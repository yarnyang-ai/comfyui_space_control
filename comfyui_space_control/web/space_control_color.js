import { app } from '../../scripts/app.js';
import { removeDuplicateColorWidgets, migrateLegacySpaceControl, migrateSpaceControlWorkflow } from './color_compat.mjs';

// Run after synchronous creation/configuration hooks from other extensions.
const clean = node => queueMicrotask(() => {
  removeDuplicateColorWidgets(node);
  if (node.comfyClass === 'ComfyUISpaceControl') {
    (node.properties ??= {}).space_control_layout = 2;
  }
});
app.registerExtension({
  name: 'SpaceControl.NativeColor',
  beforeConfigureGraph(graph) {
    migrateSpaceControlWorkflow(graph);
  },
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== 'ComfyUISpaceControl') return;
    // Migrate saved labels and defaults after ComfyUI has loaded the saved values.
    const original = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function (serialized) {
      const result = original?.apply(this, arguments);
      migrateLegacySpaceControl(this, serialized);
      return result;
    };
  },
  nodeCreated: clean,
  loadedGraphNode: clean,
});
