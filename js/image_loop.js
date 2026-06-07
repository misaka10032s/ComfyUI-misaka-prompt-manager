import { app } from "../../scripts/app.js";

console.log("[Misaka] Image Loop JS Loading...");

app.registerExtension({
    name: "Misaka.ImageLoop",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        // MisakaLoopCkptCore / MisakaLoopPromptCore / MisakaLoopManager — auto-grow input slots
        const _loopNodeDefs = {
            "MisakaLoopCkptCore":    { prefix: "ckpt_name",    type: "STRING" },
            "MisakaLoopPromptCore":  { prefix: "prompt",       type: "MISAKA_PROMPT" },
            "MisakaLoopManager":     { prefix: "conditioning", type: "CONDITIONING" },
        };
        if (!_loopNodeDefs[nodeData.name]) return;

        const { prefix, type } = _loopNodeDefs[nodeData.name];

        const _grow = (node) => {
            let max = 0;
            for (const inp of node.inputs) {
                const m = inp.name.match(new RegExp(`^${prefix}_(\\d+)$`));
                if (m) max = Math.max(max, parseInt(m[1]));
            }
            if (max === 0) { node.addInput(`${prefix}_1`, type); max = 1; }
            const lastSlot = node.inputs.find(inp => inp.name === `${prefix}_${max}`);
            if (lastSlot && lastSlot.link != null) {
                node.addInput(`${prefix}_${max + 1}`, type);
                app.graph.setDirtyCanvas(true, true);
            }
        };

        const _trim = (node) => {
            // Remove trailing empty slots (keep at least 1).
            // Rule: only remove the last slot if both it AND the previous slot are empty.
            // This ensures removing prompt_5 from a connected 1-9 set leaves 1-8 intact.
            let max = 0;
            for (const inp of node.inputs) {
                const m = inp.name.match(new RegExp(`^${prefix}_(\\d+)$`));
                if (m) max = Math.max(max, parseInt(m[1]));
            }
            while (max > 1) {
                const slot = node.inputs.find(inp => inp.name === `${prefix}_${max}`);
                const prev = node.inputs.find(inp => inp.name === `${prefix}_${max - 1}`);
                if (slot && slot.link == null && prev && prev.link == null) {
                    node.removeInput(node.inputs.indexOf(slot));
                    max--;
                    app.graph.setDirtyCanvas(true, true);
                } else break;
            }
        };

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
            _grow(this);
            return r;
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (info) {
            if (onConfigure) onConfigure.apply(this, arguments);
            _grow(this);
        };

        const onConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (type, index, connected) {
            if (onConnectionsChange) onConnectionsChange.apply(this, arguments);
            if (type !== LiteGraph.INPUT) return;
            if (connected) _grow(this); else _trim(this);
        };
    }
});
