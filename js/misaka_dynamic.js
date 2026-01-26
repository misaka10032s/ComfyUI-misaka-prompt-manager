import { app } from "../../scripts/app.js";

console.log("[Misaka] JS Extension Loading...");

app.registerExtension({
    name: "Misaka.DynamicLoras",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        // 共用：隱藏輔助欄位函數
        const hideMisakaWidgets = (node) => {
            if (!node.widgets) return;
            const targets = ["node_map", "lora_data", "prompt_data"];
            for (const name of targets) {
                const w = node.widgets.find(x => x.name === name);
                if (w) {
                    w.type = "hidden";
                    w.computeSize = () => [0, -4]; // 讓它不佔據高度
                    w.draw = () => {}; // 禁止繪製
                    // 嘗試將其移出可視區域 (雖然 draw 已經禁止了)
                    w.y = 0; 
                }
            }
        };

        // 1. MisakaPromptManager 處理邏輯
        if (nodeData.name === "MisakaPromptManager") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
                hideMisakaWidgets(this);
                setTimeout(() => hideMisakaWidgets(this), 100);
                return r;
            };
        }

        if (nodeData.name === "MisakaProfileFactory") {
            
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
                this.dynamicLoras = true;
                hideMisakaWidgets(this); 
                
                const self = this;
                let allFiles = []; // Cache all files for filtering

                // --- Helper Logic ---

                const saveProfileData = () => {
                    const getVal = (name) => {
                        const w = self.widgets.find(x => x.name === name);
                        return w ? w.value : undefined;
                    };
                    
                    const filename = getVal("save_as_profile");
                    if (!filename || filename.trim() === "") {
                        alert("Please enter a filename in 'save_as_profile'.");
                        return;
                    }

                    // Gather Loras
                    const loras = [];
                    let i = 1;
                    while (true) {
                        const name = getVal(`lora_${i}`);
                        if (!name || name === "None") break;
                        loras.push({
                            name: name,
                            strength_model: parseFloat(getVal(`l${i}_strength_model`) || 1.0),
                            strength_clip: parseFloat(getVal(`l${i}_strength_clip`) || 1.0)
                        });
                        i++;
                    }

                    let noteContent = "";
                    if (app.graph && app.graph._nodes) {
                        const noteNode = app.graph._nodes.find(n => n.title === "note" && n.type === "CLIPTextEncode");
                        if (noteNode && noteNode.widgets && noteNode.widgets.length > 0) {
                            noteContent = noteNode.widgets[0].value;
                        }
                    }

                    const profileData = {
                        checkpoint: getVal("checkpoint"),
                        loras: loras,
                        character: getVal("character"),
                        H: getVal("H"),
                        expression: getVal("expression"),
                        pose: getVal("pose"),
                        scene: getVal("scene"),
                        note: noteContent,
                        output_name: getVal("output_name"),
                        clip_skip: parseInt(getVal("clip_skip") || 0)
                    };

                    fetch("/misaka/save_profile", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ filename: filename, data: profileData })
                    }).then(r => {
                        if (r.ok) {
                            alert("Profile saved successfully!");
                            refreshFileList();
                        } else {
                            r.text().then(t => alert("Error saving: " + t));
                        }
                    });
                };

                const updateFilters = () => {
                    if (!allFiles.length) return;

                    // Filter 1: Top Folders
                    const topFolders = new Set();
                    allFiles.forEach(f => {
                        const parts = f.split("/");
                        if (parts.length > 1) topFolders.add(parts[0]);
                    });
                    
                    const f1 = self.widgets.find(w => w.name === "Folder Filter 1");
                    const currentF1 = f1.value;
                    f1.options.values = ["None", ...Array.from(topFolders).sort()];
                    if (!f1.options.values.includes(currentF1)) f1.value = "None";

                    // Filter 2: Sub Folders
                    const f2 = self.widgets.find(w => w.name === "Folder Filter 2");
                    const selectedF1 = f1.value;
                    const subFolders = new Set();
                    
                    if (selectedF1 !== "None") {
                        allFiles.forEach(f => {
                            if (f.startsWith(selectedF1 + "/")) {
                                const rel = f.substring(selectedF1.length + 1);
                                const parts = rel.split("/");
                                if (parts.length > 1) subFolders.add(parts[0]);
                            }
                        });
                    }
                    
                    const currentF2 = f2.value;
                    f2.options.values = ["None", ...Array.from(subFolders).sort()];
                    if (!f2.options.values.includes(currentF2)) f2.value = "None";
                    
                    updateSelector();
                };

                const updateSelector = () => {
                    const f1 = self.widgets.find(w => w.name === "Folder Filter 1").value;
                    const f2 = self.widgets.find(w => w.name === "Folder Filter 2").value;
                    const selector = self.widgets.find(w => w.name === "profile_selector");
                    
                    let filtered = allFiles;
                    if (f1 !== "None") {
                        filtered = filtered.filter(f => f.startsWith(f1 + "/"));
                        if (f2 !== "None") {
                             filtered = filtered.filter(f => f.startsWith(f1 + "/" + f2 + "/"));
                        }
                    }
                    
                    selector.options.values = filtered;
                    if (!filtered.includes(selector.value)) {
                        selector.value = filtered.length > 0 ? filtered[0] : "None";
                    }
                };
                
                const refreshFileList = () => {
                    fetch("/misaka/profile_list").then(r => r.json()).then(files => {
                        allFiles = files;
                        updateFilters();
                    });
                };

                const syncSaveAsFilename = () => {
                     const sel = self.widgets.find(w => w.name === "profile_selector");
                     const saveAs = self.widgets.find(w => w.name === "save_as_profile");
                     const ckptWidget = self.widgets.find(w => w.name === "checkpoint");

                     if (sel && saveAs && sel.value && sel.value !== "Loading..." && sel.value !== "None") {
                         let val = sel.value;
                         if (ckptWidget && ckptWidget.value) {
                             const ckptName = ckptWidget.value;
                             const lastDot = ckptName.lastIndexOf('.');
                             const stem = lastDot > 0 ? ckptName.substring(0, lastDot) : ckptName;
                             
                             if (val.startsWith(stem + "/")) {
                                 val = val.substring(stem.length + 1);
                             } else if (val.startsWith(stem + "\\")) {
                                 val = val.substring(stem.length + 1);
                             }
                         }
                         saveAs.value = val;
                     }
                };

                // --- UI Construction ---
                
                // 1. Save & Load Buttons
                const saveBtn = this.addWidget("button", "Save Profile (No Run)", null, saveProfileData);
                const loadBtn = this.addWidget("button", "Load Profile", null, () => {
                    const selector = self.widgets.find(w => w.name === "profile_selector");
                    if (selector && selector.value) {
                        loadProfileData(self, selector.value);
                    }
                });
                
                // 2. Filters & Selector
                const filter1 = this.addWidget("combo", "Folder Filter 1", "None", () => { updateFilters(); }, { values: ["None"] });
                const filter2 = this.addWidget("combo", "Folder Filter 2", "None", () => { updateSelector(); }, { values: ["None"] });
                const selector = this.addWidget("combo", "profile_selector", "Loading...", () => {}, { values: ["Loading..."] });
                
                // 3. Overwrite Button
                const overwriteBtn = this.addWidget("button", "Overwrite Filename", null, syncSaveAsFilename);

                // --- Reorder Widgets ---
                // Pop newly added widgets (Reverse order of creation)
                this.widgets.pop(); // overwrite
                this.widgets.pop(); // selector
                this.widgets.pop(); // filter2
                this.widgets.pop(); // filter1
                this.widgets.pop(); // loadBtn
                this.widgets.pop(); // saveBtn

                // Place Top Widgets
                this.widgets.unshift(selector);
                this.widgets.unshift(filter2);
                this.widgets.unshift(filter1);
                this.widgets.unshift(loadBtn);
                this.widgets.unshift(saveBtn);

                // Insert Overwrite Button
                const saveAsIdx = this.widgets.findIndex(w => w.name === "save_as_profile");
                if (saveAsIdx > -1) {
                    this.widgets.splice(saveAsIdx, 0, overwriteBtn);
                }

                refreshFileList();

                // 4. Load Logic
                const loadProfileData = (node, profileName) => {
                    const currentWidth = node.size[0]; // 鎖定寬度
                    
                    fetch(`/misaka/load_profile?name=${encodeURIComponent(profileName)}`)
                        .then(r => r.json())
                        .then(data => {
                            if (!data) return;
                            
                            // A. 填入標準欄位
                            const setVal = (name, val) => {
                                const w = node.widgets.find(x => x.name === name);
                                if (w && val !== undefined) w.value = val;
                            };
                            
                            setVal("checkpoint", data.checkpoint);
                            setVal("clip_skip", data.clip_skip ?? 0); 
                            setVal("output_name", data.output_name);
                            
                            if (data.positive && typeof data.positive === "string") {
                                setVal("character", data.positive);
                            } else {
                                setVal("character", data.character);
                                setVal("H", data.H);
                                setVal("expression", data.expression);
                                setVal("pose", data.pose);
                                setVal("scene", data.scene);
                            }

                            // Update "note" node if exists
                            if (data.note !== undefined && app.graph && app.graph._nodes) {
                                const noteNode = app.graph._nodes.find(n => n.title === "note" && n.type === "CLIPTextEncode");
                                if (noteNode && noteNode.widgets && noteNode.widgets.length > 0) {
                                    noteNode.widgets[0].value = data.note;
                                }
                            }

                            // B. 重建 Loras
                            if (node.widgets) {
                                for (const w of node.widgets) {
                                    if (w.name.startsWith("lora_")) {
                                        w.value = "None";
                                    }
                                }
                            }
                            const lora1 = node.widgets.find(w => w.name === "lora_1");
                            if (lora1 && lora1.callback) {
                                lora1.callback("None"); 
                            }
                            
                            const loras = data.loras || [];
                            
                            if (lora1 && loras.length > 0) {
                                lora1.value = loras[0].name;
                                setVal("l1_strength_model", loras[0].strength_model);
                                setVal("l1_strength_clip", loras[0].strength_clip);
                            }
                            
                            for (let i = 1; i < loras.length; i++) {
                                const idx = i + 1;
                                node.addLoraGroup(idx);
                                const wName = `lora_${idx}`;
                                const w = node.widgets.find(x => x.name === wName);
                                if (w) {
                                    w.value = loras[i].name;
                                    setVal(`l${idx}_strength_model`, loras[i].strength_model);
                                    setVal(`l${idx}_strength_clip`, loras[i].strength_clip);
                                }
                            }
                            
                            // Ensure next empty slot exists
                            if (loras.length > 0) {
                                node.addLoraGroup(loras.length + 1);
                            }
                            
                            // 恢復寬度，重新計算高度
                            const minH = node.computeSize()[1];
                            node.setSize([currentWidth, minH]);
                            
                            app.graph.setDirtyCanvas(true, true);
                            syncSaveAsFilename();
                            // alert(`Loaded profile: ${profileName}`); // Remove alert for better UX? User knows.
                        })
                        .catch(e => {
                            alert("Error loading profile: " + e);
                        });
                };

                this.setupDynamicLogic();
                return r;
            };

            const onConfigure = nodeType.prototype.onConfigure;
            nodeType.prototype.onConfigure = function(w) {
                if (onConfigure) onConfigure.apply(this, arguments);
                hideMisakaWidgets(this);
                
                if (w && w.widgets_values) {
                    const savedValueCount = w.widgets_values.length;
                    const currentWidgetCount = this.widgets ? this.widgets.length : 0;
                    
                    // 如果存檔的值比現在的欄位多，說明有動態增加的 Lora
                    if (savedValueCount > currentWidgetCount) {
                        const extra = savedValueCount - currentWidgetCount;
                        // 每組 3 個
                        const groupsToAdd = Math.floor(extra / 3);
                        
                        if (groupsToAdd > 0) {
                            const baseWidget = this.widgets.find(w => w.name === "lora_1");
                            const loraList = baseWidget ? baseWidget.options.values : [];

                            // 從 2 開始加
                            for (let i = 0; i < groupsToAdd; i++) {
                                const index = i + 2;
                                const widgetName = `lora_${index}`;
                                
                                // 直接加在最後面
                                const loraWidget = this.addWidget("combo", widgetName, ["None", ...loraList], (v) => {}, { values: loraList });
                                // 預設值必須是字串 "None"
                                loraWidget.value = "None"; 
                                
                                this.addWidget("number", `l${index}_strength_model`, 1.0, (v) => {}, { step: 0.01, min: -10.0, max: 10.0 });
                                this.addWidget("number", `l${index}_strength_clip`, 1.0, (v) => {}, { step: 0.01, min: -10.0, max: 10.0 });
                            }
                            
                            // 修正 ComfyUI 自動填值後的型別問題
                            // 因為我們是在 onConfigure 之後才加 Widget，ComfyUI 可能已經填完值了 (只填了前面幾個)，
                            // 或者是因為我們在 onConfigure 裡面加，ComfyUI 還沒填？
                            // 實際上，onConfigure 的參數 w 包含了 values，但 ComfyUI 的 LGraphNode.configure 
                            // 會在呼叫 onConfigure 之後，根據 widgets 的數量去填 widgets_values。
                            // 所以我們在這裡加 widget 是對的。
                            
                            // 但是，如果 ComfyUI 已經嘗試把某些值填進去了，可能會出錯。
                            // 為了保險，我們手動從 w.widgets_values 填入正確的值給新加的 widgets
                            // 以確保它們有正確的初始狀態
                            
                            // 從 currentWidgetCount 開始填
                            for (let i = currentWidgetCount; i < this.widgets.length; i++) {
                                if (i < w.widgets_values.length) {
                                    let val = w.widgets_values[i];
                                    // 如果是 Combo，強制轉字串
                                    if (this.widgets[i].type === "combo") {
                                        if (val === undefined || val === null) val = "None";
                                        this.widgets[i].value = String(val);
                                    } else {
                                        this.widgets[i].value = val;
                                    }
                                }
                            }
                        }
                    }
                }
                
                this.setupDynamicLogic();
            };

            nodeType.prototype.setupDynamicLogic = function() {
                hideMisakaWidgets(this);

                const refreshLoras = () => {
                    if (!this.widgets) return;
                    hideMisakaWidgets(this);

                    let i = 1;
                    while (true) {
                        const currentName = `lora_${i}`;
                        const currentWidget = this.widgets.find(w => w.name === currentName);

                        if (!currentWidget) {
                            const prevName = `lora_${i-1}`;
                            const prevWidget = this.widgets.find(w => w.name === prevName);
                            if (prevWidget && prevWidget.value !== "None") {
                                this.addLoraGroup(i);
                            }
                            break; 
                        }

                        // 型別保護：確保 value 是字串
                        if (typeof currentWidget.value !== 'string') {
                            currentWidget.value = String(currentWidget.value || "None");
                        }

                        if (currentWidget.value === "None") {
                            this.removeLoraGroupsFrom(i + 1);
                            break;
                        } 
                        
                        i++;
                        if (i > 100) break;
                    }
                    
                    if (this.onResize) this.onResize(this.size);
                    app.graph.setDirtyCanvas(true, true);
                };

                if (this.widgets) {
                    for (const w of this.widgets) {
                        if (w.name && w.name.startsWith("lora_") && w.name.split("_").length === 2) {
                            // 再次確保所有現有 lora widget 都是字串
                            if (typeof w.value !== 'string') w.value = String(w.value || "None");

                            if (!w.hasMisakaCallback) {
                                const originalCallback = w.callback;
                                w.callback = (value, ...args) => {
                                    if (originalCallback) originalCallback(value, ...args);
                                    refreshLoras();
                                };
                                w.hasMisakaCallback = true;
                            }
                        }
                    }
                }
                
                setTimeout(() => hideMisakaWidgets(this), 100);
                setTimeout(() => hideMisakaWidgets(this), 500);
            };

            nodeType.prototype.addLoraGroup = function(index) {
                const widgetName = `lora_${index}`;
                if (this.widgets.find(w => w.name === widgetName)) return;

                const baseWidget = this.widgets.find(w => w.name === "lora_1");
                const loraList = baseWidget ? baseWidget.options.values : [];

                const loraWidget = this.addWidget("combo", widgetName, ["None", ...loraList], (v) => {}, { values: loraList });
                loraWidget.value = "None";
                this.addWidget("number", `l${index}_strength_model`, 1.0, (v) => {}, { step: 0.01, min: -10.0, max: 10.0 });
                this.addWidget("number", `l${index}_strength_clip`, 1.0, (v) => {}, { step: 0.01, min: -10.0, max: 10.0 });

                this.setupDynamicLogic(); 
            };

            nodeType.prototype.removeLoraGroupsFrom = function(startIndex) {
                let changed = false;
                const widgetsToRemove = [];
                for (const w of this.widgets) {
                    let idx = -1;
                    if (w.name.startsWith("lora_")) {
                        idx = parseInt(w.name.split("_")[1]);
                    } else if (w.name.match(/^l\d+_strength_/)) {
                        idx = parseInt(w.name.match(/^l(\d+)_/)[1]);
                    }
                    
                    if (idx >= startIndex) {
                        widgetsToRemove.push(w);
                    }
                }

                if (widgetsToRemove.length > 0) {
                    for (const w of widgetsToRemove) {
                        const i = this.widgets.indexOf(w);
                        if (i > -1) {
                            this.widgets.splice(i, 1);
                            changed = true;
                        }
                    }
                }
                
                if (changed) {
                    const minH = this.computeSize()[1];
                    this.setSize([this.size[0], minH]);
                }
            };
        }
        // 3. MisakaPromptBuilder 處理邏輯 (動態 Prompt)
        if (nodeData.name === "MisakaPromptBuilder") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
                hideMisakaWidgets(this);
                this.setupTextLogic();
                setTimeout(() => hideMisakaWidgets(this), 100);
                return r;
            };

            const onSerialize = nodeType.prototype.onSerialize;
            nodeType.prototype.onSerialize = function(o) {
                if (onSerialize) onSerialize.apply(this, arguments);
                
                const promptDataWidget = this.widgets ? this.widgets.find(w => w.name === "prompt_data") : null;
                if (promptDataWidget) {
                    const texts = [];
                    // Start from text_2 because text_1 is standard input
                    let i = 2;
                    while (true) {
                        const w = this.widgets.find(x => x.name === `text_${i}`);
                        if (!w) break;
                        texts.push(w.value);
                        i++;
                    }
                    promptDataWidget.value = JSON.stringify(texts);
                }
            };

            const onConfigure = nodeType.prototype.onConfigure;
            nodeType.prototype.onConfigure = function(w) {
                if (onConfigure) onConfigure.apply(this, arguments);
                hideMisakaWidgets(this);
                
                // 從 widgets_values 中尋找並恢復動態欄位
                if (w && w.widgets_values) {
                    let foundTexts = null;
                    
                    for (const val of w.widgets_values) {
                        if (typeof val === "string" && val.startsWith("[") && val.endsWith("]")) {
                            try {
                                const parsed = JSON.parse(val);
                                if (Array.isArray(parsed) && parsed.length > 0) {
                                    if (typeof parsed[0] === "string") {
                                        foundTexts = parsed;
                                        console.log("[Misaka] Found prompt data:", foundTexts);
                                        break;
                                    }
                                }
                            } catch (e) {}
                        }
                    }

                    if (foundTexts) {
                        for (let i = 0; i < foundTexts.length; i++) {
                            const val = foundTexts[i];
                            const widgetName = `text_${i + 2}`; 
                            
                            // 如果不存在則建立
                            if (!this.widgets.find(w => w.name === widgetName)) {
                                app.widgets.STRING(this, widgetName, ["STRING", { multiline: true, default: "", rows: 6 }], app);
                            }
                            
                            // 無論是否剛建立，都要更新值
                            const w = this.widgets.find(x => x.name === widgetName);
                            if (w) {
                                // 只有當值不同時才更新，避免游標跳動 (雖然在 onConfigure 裡應該沒差)
                                if (w.value !== val) {
                                    w.value = val;
                                    console.log(`[Misaka] Restored/Updated ${widgetName} = ${val}`);
                                }
                            }
                        }
                    }
                }
                
                this.setupTextLogic();
                
                // 強制重繪以解決 Widget 消失問題
                const forceRedraw = () => {
                    this.setSize(this.computeSize());
                    app.graph.setDirtyCanvas(true, true);
                };
                forceRedraw();
                setTimeout(forceRedraw, 100);
            };

            nodeType.prototype.setupTextLogic = function() {
                const refreshTexts = () => {
                    if (!this.widgets) return;

                    // 1. 找出所有 text widgets 並排序
                    const textWidgets = this.widgets
                        .filter(w => w.name.startsWith("text_"))
                        .sort((a, b) => {
                            const idxA = parseInt(a.name.split("_")[1]);
                            const idxB = parseInt(b.name.split("_")[1]);
                            return idxA - idxB;
                        });

                    if (textWidgets.length === 0) return; // Should at least have text_1

                    const lastWidget = textWidgets[textWidgets.length - 1];
                    const lastIndex = parseInt(lastWidget.name.split("_")[1]);

                    // 綁定 Callback (如果還沒綁)
                    // 檢查所有 widgets，確保都有 callback
                    for (const w of textWidgets) {
                        if (!w.hasMisakaCallback) {
                            const originalCallback = w.callback;
                            w.callback = (value, ...args) => {
                                if (originalCallback) originalCallback(value, ...args);
                                refreshTexts();
                            };
                            w.hasMisakaCallback = true;
                        }
                    }

                    // 邏輯 A: 如果最後一個有值 -> 新增下一個
                    if (lastWidget.value && lastWidget.value.trim() !== "") {
                        const nextName = `text_${lastIndex + 1}`;
                        // 確保不重複新增
                        if (!this.widgets.find(w => w.name === nextName)) {
                            app.widgets.STRING(this, nextName, ["STRING", { multiline: true, default: "", rows: 6 }], app);
                            const newW = this.widgets.find(w => w.name === nextName);
                            if (newW) {
                                newW.callback = (v) => { refreshTexts(); };
                                newW.hasMisakaCallback = true;
                            }
                            // 新增後自動調整大小 (只增不減)
                            const minSize = this.computeSize();
                            this.setSize([
                                Math.max(this.size[0], minSize[0]),
                                Math.max(this.size[1], minSize[1])
                            ]);
                        }
                    } 
                    // 邏輯 B: 如果最後一個是空的
                    else {
                        // 檢查倒數第二個
                        if (textWidgets.length > 1) { // 至少保留 text_1
                            const prevWidget = textWidgets[textWidgets.length - 2];
                            // 如果倒數第二個也是空的 -> 刪除最後一個
                            if (!prevWidget.value || prevWidget.value.trim() === "") {
                                if (lastWidget.onRemove) lastWidget.onRemove();
                                const idxToRemove = this.widgets.indexOf(lastWidget);
                                if (idxToRemove > -1) {
                                    this.widgets.splice(idxToRemove, 1);
                                    // 刪除後不調整大小 (不縮回)，維持高度
                                    app.graph.setDirtyCanvas(true, true);
                                }
                            }
                        }
                    }
                    
                    // 3. 同步數據到 prompt_data (關鍵修復：確保 JSON 隨時是最新的)
                    const promptDataWidget = this.widgets.find(w => w.name === "prompt_data");
                    if (promptDataWidget) {
                        const texts = [];
                        let i = 2;
                        while (true) {
                            const w = this.widgets.find(x => x.name === `text_${i}`);
                            if (!w) break;
                            texts.push(w.value);
                            i++;
                        }
                        promptDataWidget.value = JSON.stringify(texts);
                    }
                };
                
                // 初始執行
                refreshTexts();
            };

            nodeType.prototype.removeTextsFrom = function(startIndex) {
                let changed = false;
                const widgetsToRemove = [];
                for (const w of this.widgets) {
                    if (w.name.startsWith("text_")) {
                        const idx = parseInt(w.name.split("_")[1]);
                        if (idx >= startIndex) {
                            widgetsToRemove.push(w);
                        }
                    }
                }

                if (widgetsToRemove.length > 0) {
                    for (const w of widgetsToRemove) {
                        const i = this.widgets.indexOf(w);
                        if (i > -1) {
                            // 關鍵修正：必須呼叫 onRemove 以清除 DOM 元素
                            if (w.onRemove) {
                                w.onRemove();
                            }
                            this.widgets.splice(i, 1);
                            changed = true;
                        }
                    }
                }
                
                if (changed) {
                    this.setSize(this.computeSize());
                    app.graph.setDirtyCanvas(true, true);
                }
            };
        }

        // 共用：序列化邏輯 (兩個節點都需要)
        if (nodeData.name === "MisakaProfileFactory" || nodeData.name === "MisakaPromptManager") {
             const onSerialize = nodeType.prototype.onSerialize;
             nodeType.prototype.onSerialize = function(o) {
                if (onSerialize) onSerialize.apply(this, arguments);

                const nodeMapWidget = this.widgets ? this.widgets.find(w => w.name === "node_map") : null;
                if (nodeMapWidget) {
                    const map = {};
                    if (app.graph && app.graph._nodes) {
                        for (const n of app.graph._nodes) {
                            const title = n.title || n.type;
                            map[title] = n.id;
                        }
                    }
                    nodeMapWidget.value = JSON.stringify(map);
                }

                // Lora Data 只有 Factory 需要，但 Manager 做檢查也無妨
                const loraDataWidget = this.widgets ? this.widgets.find(w => w.name === "lora_data") : null;
                if (loraDataWidget) {
                    const loras = [];
                    let i = 1;
                    while (true) {
                        const nameWidget = this.widgets.find(w => w.name === `lora_${i}`);
                        if (!nameWidget) break;

                        if (nameWidget.value && nameWidget.value !== "None") {
                            const mStr = this.widgets.find(w => w.name === `l${i}_strength_model`);
                            const cStr = this.widgets.find(w => w.name === `l${i}_strength_clip`);
                            loras.push({
                                name: nameWidget.value,
                                strength_model: mStr ? parseFloat(mStr.value) : 1.0,
                                strength_clip: cStr ? parseFloat(cStr.value) : 1.0
                            });
                        }
                        i++;
                    }
                    loraDataWidget.value = JSON.stringify(loras);
                }
            };
        }
    }
});