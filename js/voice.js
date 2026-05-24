import { app } from "../../scripts/app.js";

console.log("[Misaka] Voice JS Loading...");

app.registerExtension({
    name: "Misaka.Voice",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        // Generic audio file upload picker for voice conversion nodes
        const _addFilePicker = (node, widgetName, accept) => {
            const pathWidget = node.widgets?.find(w => w.name === widgetName);
            if (!pathWidget) return;
            node.addWidget("button", "choose file to upload", null, () => {
                const input = document.createElement("input");
                input.type = "file";
                input.accept = accept;
                input.onchange = async () => {
                    const file = input.files[0];
                    if (!file) return;
                    const body = new FormData();
                    body.append("image", file);
                    body.append("type", "input");
                    body.append("overwrite", "true");
                    const resp = await fetch("/upload/image", { method: "POST", body });
                    if (resp.ok) {
                        pathWidget.value = (await resp.json()).name;
                        app.graph.setDirtyCanvas(true, true);
                    }
                };
                input.click();
            });
        };

        const _AUDIO_NODES = {
            "MisakaVCConvertBatch": "audio_path",
            "MisakaVCAudioInfo":    "audio_path",
            "MisakaVCAutoParams":   "audio_path",
            "MisakaVCPMGenerate":   "reference_audio",
        };

        if (_AUDIO_NODES[nodeData.name]) {
            const widgetName = _AUDIO_NODES[nodeData.name];
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
                _addFilePicker(this, widgetName, ".wav,.mp3,.flac,.ogg,.m4a,.aac");
                return r;
            };
        }

        // MisakaVCLoadModel — dedicated "📂 Browse" picker for .pth/.index files
        // Reads from ComfyUI/models/rvc/ via /misaka/rvc_*_list (not /upload/image)
        if (nodeData.name === "MisakaVCLoadModel") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
                const node = this;

                function addFilePicker(widgetName, apiEndpoint, emptyLabel) {
                    const strWidget = node.widgets?.find(w => w.name === widgetName);
                    if (!strWidget) return;

                    const btn = node.addWidget("button", `📂 ${widgetName}`, null, async () => {
                        try {
                            const resp = await fetch(apiEndpoint);
                            const files = await resp.json();
                            const options = emptyLabel ? [emptyLabel, ...files] : files;

                            if (options.length === 0) {
                                alert(`No files found.\nPlace .pth/.index files in:\n  ComfyUI/models/rvc/`);
                                return;
                            }

                            const overlay = document.createElement("div");
                            Object.assign(overlay.style, {
                                position: "fixed", top: 0, left: 0,
                                width: "100vw", height: "100vh",
                                background: "rgba(0,0,0,0.5)",
                                zIndex: 9999, display: "flex",
                                alignItems: "center", justifyContent: "center",
                            });

                            const box = document.createElement("div");
                            Object.assign(box.style, {
                                background: "#1e1e1e", borderRadius: "8px",
                                padding: "16px", minWidth: "480px", maxWidth: "80vw",
                                maxHeight: "70vh", display: "flex", flexDirection: "column",
                                gap: "8px", boxShadow: "0 8px 32px rgba(0,0,0,0.8)",
                            });

                            const title = document.createElement("div");
                            title.textContent = `選擇 ${widgetName}`;
                            Object.assign(title.style, { color: "#ccc", fontWeight: "bold", fontSize: "14px" });
                            box.appendChild(title);

                            const list = document.createElement("div");
                            Object.assign(list.style, { overflowY: "auto", flex: 1 });

                            options.forEach(f => {
                                const row = document.createElement("div");
                                const label = f === emptyLabel ? "(無 / 不使用)" : f.split("/").pop();
                                const sub = f === emptyLabel ? "" : f;
                                row.innerHTML = `<span style="color:#eee;font-size:13px">${label}</span>` +
                                    (sub ? `<br><span style="color:#888;font-size:10px">${sub}</span>` : "");
                                Object.assign(row.style, {
                                    padding: "8px 10px", cursor: "pointer",
                                    borderRadius: "4px", marginBottom: "2px",
                                });
                                row.onmouseenter = () => row.style.background = "#3a3a3a";
                                row.onmouseleave = () => row.style.background = "";
                                row.onclick = () => {
                                    strWidget.value = f === emptyLabel ? "" : f;
                                    if (strWidget.callback) strWidget.callback(strWidget.value);
                                    app.graph.setDirtyCanvas(true);
                                    document.body.removeChild(overlay);
                                };
                                list.appendChild(row);
                            });
                            box.appendChild(list);

                            const cancelBtn = document.createElement("button");
                            cancelBtn.textContent = "取消";
                            Object.assign(cancelBtn.style, {
                                alignSelf: "flex-end", padding: "4px 16px",
                                cursor: "pointer", background: "#444", border: "none",
                                color: "#fff", borderRadius: "4px",
                            });
                            cancelBtn.onclick = () => document.body.removeChild(overlay);
                            box.appendChild(cancelBtn);

                            overlay.appendChild(box);
                            overlay.onclick = (e) => { if (e.target === overlay) document.body.removeChild(overlay); };
                            document.body.appendChild(overlay);
                        } catch (err) {
                            console.error("[Misaka] file picker error:", err);
                        }
                    });

                    btn.serialize = false;
                }

                addFilePicker("model_path", "/misaka/rvc_model_list", null);
                addFilePicker("index_path", "/misaka/rvc_index_list", "(空 = 不使用 index)");

                return r;
            };
        }
    }
});
