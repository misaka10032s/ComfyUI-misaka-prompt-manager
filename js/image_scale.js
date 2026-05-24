import { app } from "../../scripts/app.js";

console.log("[Misaka] Image Scale JS Loading...");

app.registerExtension({
    name: "Misaka.ImageScale",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "MisakaScaleCustom") return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
            const self = this;

            this.addWidget("button", "Calculate", null, () => {
                const ratioWidget = self.widgets.find(w => w.name === "aspect_ratio");
                const wWidget    = self.widgets.find(w => w.name === "width");
                const hWidget    = self.widgets.find(w => w.name === "height");
                if (!ratioWidget || !wWidget || !hWidget) return;

                const ratio = ratioWidget.value;
                if (ratio === "free") return;

                const [rw, rh] = ratio.split(":").map(Number);
                const W = parseInt(wWidget.value) || 0;
                const H = parseInt(hWidget.value) || 0;

                const snap8 = v => Math.max(8, Math.round(v / 8) * 8);

                if (W > 0 && H === 0) {
                    hWidget.value = snap8(W * rh / rw);
                } else if (H > 0 && W === 0) {
                    wWidget.value = snap8(H * rw / rh);
                } else if (W > 0 && H > 0) {
                    // Width-first: recalculate height to match ratio
                    hWidget.value = snap8(W * rh / rw);
                }

                app.graph.setDirtyCanvas(true, true);
            });

            return r;
        };
    }
});
