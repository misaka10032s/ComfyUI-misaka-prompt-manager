"""
RVC synthesis network — inference-only reimplementation.
Architecture matches the original Retrieval-based-Voice-Conversion-WebUI (MIT licence)
so that .pth weight files load correctly via load_state_dict().

Supports:
  SynthesizerTrnMs256NSFsid  — v1 models (256-dim phone features)
  SynthesizerTrnMs768NSFsid  — v2 models (768-dim phone features)
"""

import math
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn import Conv1d, ConvTranspose1d
from torch.nn.utils import weight_norm, remove_weight_norm


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def sequence_mask(length, max_length=None):
    if max_length is None:
        max_length = length.max()
    x = torch.arange(max_length, dtype=length.dtype, device=length.device)
    return x.unsqueeze(0) < length.unsqueeze(1)


def get_padding(kernel_size, dilation=1):
    return int((kernel_size * dilation - dilation) / 2)


# ---------------------------------------------------------------------------
# WaveNet-style residual blocks
# ---------------------------------------------------------------------------

class WN(nn.Module):
    def __init__(self, hidden_channels, kernel_size, dilation_rate, n_layers,
                 gin_channels=0, p_dropout=0):
        super().__init__()
        assert kernel_size % 2 == 1
        self.hidden_channels = hidden_channels
        self.n_layers = n_layers
        self.gin_channels = gin_channels
        self.drop = nn.Dropout(p_dropout)

        self.in_layers = nn.ModuleList()
        self.res_skip_layers = nn.ModuleList()

        if gin_channels != 0:
            self.cond_layer = weight_norm(
                nn.Conv1d(gin_channels, 2 * hidden_channels * n_layers, 1), name="weight")

        for i in range(n_layers):
            dilation = dilation_rate ** i
            padding = get_padding(kernel_size, dilation)
            in_l = weight_norm(
                nn.Conv1d(hidden_channels, 2 * hidden_channels, kernel_size,
                          dilation=dilation, padding=padding), name="weight")
            self.in_layers.append(in_l)

            out_ch = 2 * hidden_channels if i < n_layers - 1 else hidden_channels
            self.res_skip_layers.append(
                weight_norm(nn.Conv1d(hidden_channels, out_ch, 1), name="weight"))

    def forward(self, x, x_mask, g=None, **kwargs):
        output = torch.zeros_like(x)
        n_ch = torch.IntTensor([self.hidden_channels])
        if g is not None:
            g = self.cond_layer(g)

        for i in range(self.n_layers):
            x_in = self.in_layers[i](x)
            if g is not None:
                cond_off = i * 2 * self.hidden_channels
                g_l = g[:, cond_off: cond_off + 2 * self.hidden_channels, :]
            else:
                g_l = torch.zeros_like(x_in)

            in_act = x_in + g_l
            t_act = torch.tanh(in_act[:, :n_ch[0], :])
            s_act = torch.sigmoid(in_act[:, n_ch[0]:, :])
            acts = self.drop(t_act * s_act)

            res_skip = self.res_skip_layers[i](acts)
            if i < self.n_layers - 1:
                x = (x + res_skip[:, : self.hidden_channels, :]) * x_mask
                output = output + res_skip[:, self.hidden_channels:, :]
            else:
                output = output + res_skip

        return output * x_mask

    def remove_weight_norm(self):
        if self.gin_channels != 0:
            remove_weight_norm(self.cond_layer)
        for l in self.in_layers:
            remove_weight_norm(l)
        for l in self.res_skip_layers:
            remove_weight_norm(l)


# ---------------------------------------------------------------------------
# Normalizing flow
# ---------------------------------------------------------------------------

class Flip(nn.Module):
    def forward(self, x, *args, reverse=False, **kwargs):
        x = torch.flip(x, [1])
        if not reverse:
            logdet = torch.zeros(x.size(0), dtype=x.dtype, device=x.device)
            return x, logdet
        return x


class ResidualCouplingLayer(nn.Module):
    def __init__(self, channels, hidden_channels, kernel_size, dilation_rate,
                 n_layers, p_dropout=0, gin_channels=0, mean_only=False):
        assert channels % 2 == 0
        super().__init__()
        self.half_channels = channels // 2
        self.mean_only = mean_only

        self.pre = nn.Conv1d(self.half_channels, hidden_channels, 1)
        self.enc = WN(hidden_channels, kernel_size, dilation_rate, n_layers,
                      p_dropout=p_dropout, gin_channels=gin_channels)
        out_ch = self.half_channels * (2 - mean_only)
        self.post = nn.Conv1d(hidden_channels, out_ch, 1)
        nn.init.zeros_(self.post.weight)
        nn.init.zeros_(self.post.bias)

    def forward(self, x, x_mask, g=None, reverse=False):
        x0, x1 = torch.split(x, [self.half_channels] * 2, dim=1)
        h = self.enc(self.pre(x0) * x_mask, x_mask, g=g)
        stats = self.post(h) * x_mask
        if self.mean_only:
            m, logs = stats, torch.zeros_like(stats)
        else:
            m, logs = torch.split(stats, [self.half_channels] * 2, dim=1)

        if not reverse:
            x1 = m + x1 * torch.exp(logs) * x_mask
            return torch.cat([x0, x1], 1), torch.sum(logs, [1, 2])
        else:
            x1 = (x1 - m) * torch.exp(-logs) * x_mask
            return torch.cat([x0, x1], 1)


class ResidualCouplingBlock(nn.Module):
    def __init__(self, channels, hidden_channels, kernel_size, dilation_rate,
                 n_layers, n_flows=4, gin_channels=0, wn_layers=4):
        super().__init__()
        self.flows = nn.ModuleList()
        for _ in range(n_flows):
            self.flows.append(
                ResidualCouplingLayer(channels, hidden_channels, kernel_size,
                                      dilation_rate, wn_layers,
                                      gin_channels=gin_channels, mean_only=True))
            self.flows.append(Flip())

    def forward(self, x, x_mask, g=None, reverse=False):
        flows = self.flows if not reverse else reversed(self.flows)
        for flow in flows:
            if not reverse:
                x, _ = flow(x, x_mask, g=g, reverse=False)
            else:
                x = flow(x, x_mask, g=g, reverse=True)
        return x

    def remove_weight_norm(self):
        for f in self.flows:
            if hasattr(f, "enc"):
                f.enc.remove_weight_norm()


# ---------------------------------------------------------------------------
# Transformer encoder
# ---------------------------------------------------------------------------

class LayerNorm(nn.Module):
    def __init__(self, channels, eps=1e-5):
        super().__init__()
        self.eps = eps
        self.gamma = nn.Parameter(torch.ones(channels))
        self.beta = nn.Parameter(torch.zeros(channels))

    def forward(self, x):
        x = x.transpose(1, -1)
        x = F.layer_norm(x, x.shape[-1:], self.gamma, self.beta, self.eps)
        return x.transpose(1, -1)


class MultiHeadAttention(nn.Module):
    def __init__(self, channels, out_channels, n_heads, p_dropout=0.0, window_size=None):
        super().__init__()
        assert channels % n_heads == 0
        self.n_heads = n_heads
        self.k_channels = channels // n_heads
        self.window_size = window_size

        self.conv_q = nn.Conv1d(channels, channels, 1)
        self.conv_k = nn.Conv1d(channels, channels, 1)
        self.conv_v = nn.Conv1d(channels, channels, 1)
        self.conv_o = nn.Conv1d(channels, out_channels, 1)
        self.drop = nn.Dropout(p_dropout)

        if window_size is not None:
            rel_std = self.k_channels ** -0.5
            self.emb_rel_k = nn.Parameter(
                torch.randn(1, window_size * 2 + 1, self.k_channels) * rel_std)
            self.emb_rel_v = nn.Parameter(
                torch.randn(1, window_size * 2 + 1, self.k_channels) * rel_std)

        nn.init.xavier_uniform_(self.conv_q.weight)
        nn.init.xavier_uniform_(self.conv_k.weight)
        nn.init.xavier_uniform_(self.conv_v.weight)

    def forward(self, x, c, attn_mask=None):
        q = self.conv_q(x)
        k = self.conv_k(c)
        v = self.conv_v(c)
        x, _ = self._attention(q, k, v, attn_mask)
        return self.conv_o(x)

    def _attention(self, q, k, v, mask=None):
        b, d, t_t = q.size()
        t_s = k.size(2)
        q = q.view(b, self.n_heads, self.k_channels, t_t).transpose(2, 3)
        k = k.view(b, self.n_heads, self.k_channels, t_s).transpose(2, 3)
        v = v.view(b, self.n_heads, self.k_channels, t_s).transpose(2, 3)

        scores = torch.matmul(q / math.sqrt(self.k_channels), k.transpose(-2, -1))

        if self.window_size is not None and t_s == t_t:
            rel_k = self._get_rel_emb(self.emb_rel_k, t_s)
            # relative positional bias
            rel_scores = self._rel_attn_inner(q, rel_k)
            scores = scores + rel_scores / math.sqrt(self.k_channels)

        if mask is not None:
            scores = scores.masked_fill(mask == 0, -1e4)

        p = self.drop(F.softmax(scores, dim=-1))
        out = torch.matmul(p, v)

        if self.window_size is not None and t_s == t_t:
            rel_v = self._get_rel_emb(self.emb_rel_v, t_s)
            rel_w = self._abs_to_rel(p)
            out = out + torch.matmul(rel_w, rel_v)

        out = out.transpose(2, 3).contiguous().view(b, d, t_t)
        return out, p

    def _get_rel_emb(self, emb, length):
        ws = self.window_size
        pad = max(length - (ws + 1), 0)
        start = max(ws + 1 - length, 0)
        end = start + 2 * length - 1
        if pad > 0:
            emb = F.pad(emb, (0, 0, pad, pad))
        return emb[:, start:end]

    def _rel_attn_inner(self, x, y):
        # x: (b, h, t, d_k), y: (1, 2t-1, d_k)
        b, h, t, d = x.size()
        x_flat = x.reshape(b * h, t, d)
        y = y.expand(b * h, -1, -1)          # [1, 2t-1, d] → [b*h, 2t-1, d]
        rel = torch.bmm(x_flat, y.transpose(1, 2))  # (b*h, t, 2t-1)
        rel = self._rel_to_abs(rel).view(b, h, t, t)
        return rel

    def _rel_to_abs(self, x):
        b, t, _ = x.size()
        x = F.pad(x, (0, 1)).view(b, -1)
        x = F.pad(x, (0, t - 1)).view(b, t + 1, 2 * t - 1)
        return x[:, :t, t - 1:]

    def _abs_to_rel(self, x):
        b, h, t, _ = x.size()
        x = x.reshape(b * h, t, t)
        x = F.pad(x, (0, t - 1)).reshape(b * h, -1)
        x = F.pad(x, (t, 0)).reshape(b * h, t, 2 * t)
        return x[:, :, 1:].reshape(b, h, t, 2 * t - 1)


class FFN(nn.Module):
    def __init__(self, in_ch, out_ch, filter_ch, kernel_size, p_dropout=0.0):
        super().__init__()
        self.conv_1 = nn.Conv1d(in_ch, filter_ch, kernel_size)
        self.conv_2 = nn.Conv1d(filter_ch, out_ch, kernel_size)
        self.drop = nn.Dropout(p_dropout)
        self.pad = (kernel_size - 1) // 2, kernel_size // 2

    def forward(self, x, x_mask):
        x = F.pad(x * x_mask, [self.pad[0], self.pad[1]])
        x = torch.relu(self.conv_1(x))
        x = self.drop(x)
        x = F.pad(x * x_mask, [self.pad[0], self.pad[1]])
        return self.conv_2(x) * x_mask


class Encoder(nn.Module):
    def __init__(self, hidden_channels, filter_channels, n_heads, n_layers,
                 kernel_size=1, p_dropout=0.0, window_size=4):
        super().__init__()
        self.drop = nn.Dropout(p_dropout)
        self.attn_layers = nn.ModuleList()
        self.norm_layers_1 = nn.ModuleList()
        self.ffn_layers = nn.ModuleList()
        self.norm_layers_2 = nn.ModuleList()
        for _ in range(n_layers):
            self.attn_layers.append(
                MultiHeadAttention(hidden_channels, hidden_channels, n_heads,
                                   p_dropout=p_dropout, window_size=window_size))
            self.norm_layers_1.append(LayerNorm(hidden_channels))
            self.ffn_layers.append(
                FFN(hidden_channels, hidden_channels, filter_channels, kernel_size,
                    p_dropout=p_dropout))
            self.norm_layers_2.append(LayerNorm(hidden_channels))

    def forward(self, x, x_mask):
        attn_mask = x_mask.unsqueeze(2) * x_mask.unsqueeze(-1)
        x = x * x_mask
        for attn, norm1, ffn, norm2 in zip(
                self.attn_layers, self.norm_layers_1,
                self.ffn_layers, self.norm_layers_2):
            y = self.drop(attn(x, x, attn_mask))
            x = norm1(x + y)
            y = self.drop(ffn(x, x_mask))
            x = norm2(x + y)
        return x * x_mask


# ---------------------------------------------------------------------------
# Text encoders (one per model version)
# ---------------------------------------------------------------------------

class TextEncoder256(nn.Module):
    def __init__(self, out_channels, hidden_channels, filter_channels, n_heads,
                 n_layers, kernel_size, p_dropout, f0=True, window_size=4):
        super().__init__()
        self.out_channels = out_channels
        self.emb_phone = nn.Linear(256, hidden_channels)
        self.lrelu = nn.LeakyReLU(0.1, inplace=True)
        if f0:
            self.emb_pitch = nn.Embedding(256, hidden_channels)
        self.encoder = Encoder(hidden_channels, filter_channels, n_heads, n_layers,
                               kernel_size, p_dropout, window_size=window_size)
        self.proj = nn.Conv1d(hidden_channels, out_channels * 2, 1)

    def forward(self, phone, pitch, lengths):
        x = self.emb_phone(phone)
        if pitch is not None and hasattr(self, "emb_pitch"):
            x = x + self.emb_pitch(pitch)
        x = self.lrelu(x * math.sqrt(x.size(-1)))
        x = x.transpose(1, 2)
        x_mask = sequence_mask(lengths, x.size(2)).unsqueeze(1).to(x.dtype)
        x = self.encoder(x * x_mask, x_mask)
        stats = self.proj(x) * x_mask
        m, logs = torch.split(stats, self.out_channels, dim=1)
        return m, logs, x_mask


class TextEncoder768(nn.Module):
    def __init__(self, out_channels, hidden_channels, filter_channels, n_heads,
                 n_layers, kernel_size, p_dropout, f0=True, window_size=4):
        super().__init__()
        self.out_channels = out_channels
        self.emb_phone = nn.Linear(768, hidden_channels)
        self.lrelu = nn.LeakyReLU(0.1, inplace=True)
        if f0:
            self.emb_pitch = nn.Embedding(256, hidden_channels)
        self.encoder = Encoder(hidden_channels, filter_channels, n_heads, n_layers,
                               kernel_size, p_dropout, window_size=window_size)
        self.proj = nn.Conv1d(hidden_channels, out_channels * 2, 1)

    def forward(self, phone, pitch, lengths):
        x = self.emb_phone(phone)
        if pitch is not None and hasattr(self, "emb_pitch"):
            x = x + self.emb_pitch(pitch)
        x = self.lrelu(x * math.sqrt(x.size(-1)))
        x = x.transpose(1, 2)
        x_mask = sequence_mask(lengths, x.size(2)).unsqueeze(1).to(x.dtype)
        x = self.encoder(x * x_mask, x_mask)
        stats = self.proj(x) * x_mask
        m, logs = torch.split(stats, self.out_channels, dim=1)
        return m, logs, x_mask


# ---------------------------------------------------------------------------
# NSF (Neural Source Filter) vocoder
# ---------------------------------------------------------------------------

class SineGen(nn.Module):
    """
    Generates harmonic sine waves at audio sample rate from frame-rate F0.
    f0 input:  (B, T_frame)  — frame-rate fundamental frequency in Hz
    upp:       int           — upsampling factor (sample_rate / frame_rate)
    outputs:   sines  (B, T_frame*upp, dim)
               uv     (B, T_frame*upp, 1)
               noise  (B, T_frame*upp, dim)
    """

    def __init__(self, samp_rate, harmonic_num=0, sine_amp=0.1,
                 noise_std=0.003, voiced_threshold=0):
        super().__init__()
        self.sine_amp = sine_amp
        self.noise_std = noise_std
        self.harmonic_num = harmonic_num
        self.sampling_rate = samp_rate
        self.voiced_threshold = voiced_threshold
        self.dim = harmonic_num + 1

    def forward(self, f0, upp: int):
        with torch.no_grad():
            B, T = f0.shape
            T_s = T * upp  # target sample count

            # Upsample F0 to sample rate (nearest neighbour)
            f0_s = F.interpolate(f0.unsqueeze(1).float(), size=T_s,
                                 mode="nearest").squeeze(1)  # (B, T_s)

            # Build harmonic frequencies
            f0_buf = torch.zeros(B, self.dim, T_s, device=f0.device)
            for i in range(self.dim):
                f0_buf[:, i, :] = f0_s * (i + 1)

            # Cumulative instantaneous phase
            rad = (f0_buf / self.sampling_rate) % 1.0
            rand_ini = torch.rand(B, self.dim, 1, device=f0.device)
            rand_ini[:, 0, :] = 0.0
            rad[:, :, 0] = rad[:, :, 0] + rand_ini[:, :, 0]
            cumsums = torch.cumsum(rad, dim=2) % 1.0
            over = (cumsums[:, :, 1:] - cumsums[:, :, :-1]) < 0
            shift = torch.zeros_like(rad)
            shift[:, :, 1:] = over.float() * -1.0
            sines = torch.sin(torch.cumsum(rad + shift, dim=2) * 2 * math.pi
                              ) * self.sine_amp  # (B, dim, T_s)

            # Voiced / unvoiced mask at sample rate
            uv = (f0_s > self.voiced_threshold).float()  # (B, T_s)
            noise_amp = uv * self.noise_std + (1 - uv) * self.sine_amp / 3
            noise = noise_amp.unsqueeze(1) * torch.randn_like(sines)
            sines = sines * uv.unsqueeze(1) + noise

        # (B, dim, T_s) → (B, T_s, dim)
        return sines.transpose(1, 2), uv.unsqueeze(2), noise.transpose(1, 2)


class SourceModuleHnNSF(nn.Module):
    def __init__(self, sampling_rate, harmonic_num=0, sine_amp=0.1,
                 add_noise_std=0.003, voiced_threshold=0):
        super().__init__()
        self.sine_amp = sine_amp
        self.noise_std = add_noise_std
        self.l_sin_gen = SineGen(sampling_rate, harmonic_num, sine_amp,
                                 add_noise_std, voiced_threshold)
        self.l_linear = nn.Linear(harmonic_num + 1, 1)
        self.l_tanh = nn.Tanh()

    def forward(self, x, upp=None):
        sine_wavs, uv, _ = self.l_sin_gen(x, upp)
        sine_merge = self.l_tanh(self.l_linear(sine_wavs))
        return sine_merge, None, None


# ---------------------------------------------------------------------------
# HiFi-GAN generator (ResBlock1)
# ---------------------------------------------------------------------------

class ResBlock1(nn.Module):
    def __init__(self, channels, kernel_size=3, dilation=(1, 3, 5)):
        super().__init__()
        self.convs1 = nn.ModuleList([
            weight_norm(Conv1d(channels, channels, kernel_size, 1,
                               dilation=d, padding=get_padding(kernel_size, d)))
            for d in dilation
        ])
        self.convs2 = nn.ModuleList([
            weight_norm(Conv1d(channels, channels, kernel_size, 1,
                               dilation=1, padding=get_padding(kernel_size, 1)))
            for _ in dilation
        ])

    def forward(self, x, x_mask=None):
        for c1, c2 in zip(self.convs1, self.convs2):
            xt = F.leaky_relu(x, 0.1)
            xt = c1(xt if x_mask is None else xt * x_mask)
            xt = c2(F.leaky_relu(xt, 0.1) * (1 if x_mask is None else x_mask))
            x = x + xt
        return x if x_mask is None else x * x_mask

    def remove_weight_norm(self):
        for l in self.convs1 + self.convs2:
            remove_weight_norm(l)


class GeneratorNSF(nn.Module):
    def __init__(self, initial_channel, resblock_kernel_sizes, resblock_dilation_sizes,
                 upsample_rates, upsample_initial_channel, upsample_kernel_sizes,
                 gin_channels, sr, is_half=False):
        super().__init__()
        self.num_kernels = len(resblock_kernel_sizes)
        self.num_upsamples = len(upsample_rates)
        self.f0_upsamp = torch.nn.Upsample(scale_factor=math.prod(upsample_rates))
        self.m_source = SourceModuleHnNSF(sampling_rate=sr, harmonic_num=0)
        self.noise_convs = nn.ModuleList()

        self.conv_pre = weight_norm(
            Conv1d(initial_channel, upsample_initial_channel, 7, 1, padding=3))
        self.ups = nn.ModuleList()

        ch = upsample_initial_channel
        for i, (u, k) in enumerate(zip(upsample_rates, upsample_kernel_sizes)):
            self.ups.append(weight_norm(
                ConvTranspose1d(ch, ch // 2, k, u,
                                padding=(k - u) // 2)))
            ch //= 2
            stride_f0 = math.prod(upsample_rates[i + 1:])
            if stride_f0 > 1:
                self.noise_convs.append(
                    Conv1d(1, ch, kernel_size=stride_f0 * 2, stride=stride_f0,
                           padding=stride_f0 // 2))
            else:
                self.noise_convs.append(Conv1d(1, ch, kernel_size=1))

        self.resblocks = nn.ModuleList()
        for i in range(len(self.ups)):
            ch_now = upsample_initial_channel // (2 ** (i + 1))
            for k, d in zip(resblock_kernel_sizes, resblock_dilation_sizes):
                self.resblocks.append(ResBlock1(ch_now, k, d))

        self.conv_post = weight_norm(Conv1d(ch, 1, 7, 1, padding=3, bias=False))
        self.ups.apply(self._init_weights)

        if gin_channels != 0:
            self.cond = nn.Conv1d(gin_channels, upsample_initial_channel, 1)

    @staticmethod
    def _init_weights(m):
        if isinstance(m, (Conv1d, ConvTranspose1d)):
            nn.init.normal_(m.weight, 0.0, 0.01)

    def forward(self, x, f0, g=None):
        # f0: (B, T_frame) at frame rate — SineGen handles upsampling internally
        upp = int(self.f0_upsamp.scale_factor)
        har_source, _, _ = self.m_source(f0, upp)
        har_source = har_source.transpose(1, 2)  # (B, 1, T_sample)

        x = self.conv_pre(x)
        if g is not None:
            x = x + self.cond(g)

        for i, (up, noise_conv) in enumerate(zip(self.ups, self.noise_convs)):
            x = F.leaky_relu(x, 0.1)
            x = up(x)
            x = x + noise_conv(har_source)
            xs = None
            for j in range(self.num_kernels):
                block = self.resblocks[i * self.num_kernels + j]
                xs = block(x) if xs is None else xs + block(x)
            x = xs / self.num_kernels

        x = F.leaky_relu(x)
        x = torch.tanh(self.conv_post(x))
        return x

    def remove_weight_norm(self):
        remove_weight_norm(self.conv_pre)
        remove_weight_norm(self.conv_post)
        for l in self.ups:
            remove_weight_norm(l)
        for l in self.resblocks:
            l.remove_weight_norm()


# ---------------------------------------------------------------------------
# Top-level synthesizers
# ---------------------------------------------------------------------------

class SynthesizerTrnMs256NSFsid(nn.Module):
    def __init__(self, spec_channels, segment_size, inter_channels, hidden_channels,
                 filter_channels, n_heads, n_layers, kernel_size, p_dropout,
                 resblock, resblock_kernel_sizes, resblock_dilation_sizes,
                 upsample_rates, upsample_initial_channel, upsample_kernel_sizes,
                 spk_embed_dim, gin_channels, sr,
                 window_size=4, flow_wn_layers=4, **kwargs):
        super().__init__()
        self.inter_channels = inter_channels
        self.enc_p = TextEncoder256(inter_channels, hidden_channels, filter_channels,
                                    n_heads, n_layers, kernel_size, p_dropout,
                                    window_size=window_size)
        self.dec = GeneratorNSF(inter_channels, resblock_kernel_sizes,
                                resblock_dilation_sizes, upsample_rates,
                                upsample_initial_channel, upsample_kernel_sizes,
                                gin_channels, sr)
        self.flow = ResidualCouplingBlock(inter_channels, hidden_channels,
                                          5, 1, 4, gin_channels=gin_channels,
                                          wn_layers=flow_wn_layers)
        self.emb_g = nn.Embedding(spk_embed_dim, gin_channels)

    def remove_weight_norm(self):
        self.dec.remove_weight_norm()
        self.flow.remove_weight_norm()

    def infer(self, phone, phone_lengths, pitch, nsff0, sid, max_len=None):
        g = self.emb_g(sid).unsqueeze(-1)
        m_p, logs_p, x_mask = self.enc_p(phone, pitch, phone_lengths)
        z_p = (m_p + torch.exp(logs_p) * torch.randn_like(m_p) * 0.33) * x_mask
        z = self.flow(z_p, x_mask, g=g, reverse=True)
        o = self.dec((z * x_mask)[:, :, :max_len], nsff0[:, :max_len], g=g)
        return o, x_mask


class SynthesizerTrnMs768NSFsid(nn.Module):  # v2
    def __init__(self, spec_channels, segment_size, inter_channels, hidden_channels,
                 filter_channels, n_heads, n_layers, kernel_size, p_dropout,
                 resblock, resblock_kernel_sizes, resblock_dilation_sizes,
                 upsample_rates, upsample_initial_channel, upsample_kernel_sizes,
                 spk_embed_dim, gin_channels, sr,
                 window_size=4, flow_wn_layers=4, **kwargs):
        super().__init__()
        self.inter_channels = inter_channels
        self.enc_p = TextEncoder768(inter_channels, hidden_channels, filter_channels,
                                    n_heads, n_layers, kernel_size, p_dropout,
                                    window_size=window_size)
        self.dec = GeneratorNSF(inter_channels, resblock_kernel_sizes,
                                resblock_dilation_sizes, upsample_rates,
                                upsample_initial_channel, upsample_kernel_sizes,
                                gin_channels, sr)
        self.flow = ResidualCouplingBlock(inter_channels, hidden_channels,
                                          5, 1, 4, gin_channels=gin_channels,
                                          wn_layers=flow_wn_layers)
        self.emb_g = nn.Embedding(spk_embed_dim, gin_channels)

    def remove_weight_norm(self):
        self.dec.remove_weight_norm()
        self.flow.remove_weight_norm()

    def infer(self, phone, phone_lengths, pitch, nsff0, sid, max_len=None):
        g = self.emb_g(sid).unsqueeze(-1)
        m_p, logs_p, x_mask = self.enc_p(phone, pitch, phone_lengths)
        z_p = (m_p + torch.exp(logs_p) * torch.randn_like(m_p) * 0.33) * x_mask
        z = self.flow(z_p, x_mask, g=g, reverse=True)
        o = self.dec((z * x_mask)[:, :, :max_len], nsff0[:, :max_len], g=g)
        return o, x_mask
