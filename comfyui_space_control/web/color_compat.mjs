/** Keep the first color widget and dispose of duplicates added by legacy extensions. */
export function removeDuplicateColorWidgets(node) {
  if (node.comfyClass !== 'ComfyUISpaceControl' || !node.widgets) return;
  let found = false;
  node.widgets = node.widgets.filter(widget => {
    if (widget.name !== 'color') return true;
    if (!found) {
      found = true;
      return true;
    }
    widget.onRemove?.();
    return false;
  });
}

const legacyPositions = {
  '上': 'top', '下': 'bottom', '左': 'left', '右': 'right',
  '左上': 'top_left', '右上': 'top_right',
  '左下': 'bottom_left', '右下': 'bottom_right',
  '中央': 'center', '全周': 'all_edges', 'perimeter': 'all_edges',
};

const legacyNodeTitles = new Set(['Space Control', 'Space Control / 余白の下地']);

const removedInputs = new Set(['clip', 'positive', 'contents', 'contents_strength']);
const controlNames = ['position', 'width_ratio', 'strength', 'space_mode', 'color', 'seed'];

function isSpaceControlNode(node) {
  if (node.type === 'ComfyUISpaceControl') return true;
  const names = new Set((node.inputs ?? []).map(input => input.name));
  return node.type?.startsWith('ComfyUISpace') &&
    ['model', 'vae', 'latent'].every(name => names.has(name));
}

/** Normalize earlier names from this node family before restoring its sockets. */
function normalizeControlNames(node) {
  const previousType = node.type;
  const previousTitle = previousType.replace(/^ComfyUI/, '').replace(/^Space/, 'Space ');
  node.type = 'ComfyUISpaceControl';
  if (node.title === previousTitle || node.title === `${previousTitle} / 余白の下地`) {
    node.title = 'Space Control';
  }
  const canonicalName = name => name?.endsWith('_mode') ? 'space_mode'
    : name?.endsWith('_seed') ? 'seed' : name;
  for (const input of node.inputs ?? []) {
    input.name = canonicalName(input.name);
    if (input.widget) input.widget.name = canonicalName(input.widget.name);
  }
  const named = node.widgets_values_named;
  for (const name of Object.keys(named ?? {})) {
    const canonical = canonicalName(name);
    if (canonical === name) continue;
    if (!Object.hasOwn(named, canonical)) named[canonical] = named[name];
    delete named[name];
  }
  const properties = node.properties ??= {};
  for (const name of Object.keys(properties)) {
    if (name === 'space_control_layout' || !name.startsWith('space_') || !name.endsWith('_layout')) continue;
    properties.space_control_layout ??= properties[name];
    delete properties[name];
  }
  if (properties['Node name for S&R'] === previousType) {
    properties['Node name for S&R'] = node.type;
  }
}

function baseValues(serialized) {
  const saved = serialized.widgets_values;
  if (!Array.isArray(saved)) return null;
  const currentLayout = serialized.properties?.space_control_layout >= 2 ||
    (typeof saved[3] === 'string' && typeof saved[4] === 'string' && saved[4].startsWith('#'));
  const legacyValues = saved.length === 5
    ? [...saved.slice(0, 4), 'color', 0]
    : saved.length >= 7
      ? [...saved.slice(0, 4), saved[5], saved[6]]
      : [...saved];
  const values = currentLayout ? [...saved.slice(0, 6)]
    : [legacyValues[0], legacyValues[1], legacyValues[2], legacyValues[4], legacyValues[3], legacyValues[5]];
  const named = serialized.widgets_values_named;
  for (const [i, name] of controlNames.entries()) {
    if (named && Object.hasOwn(named, name)) values[i] = named[name];
  }
  values[0] = legacyPositions[values[0]] ?? values[0];
  return values;
}

// Restore by name after loading a saved node, including the former widget layout.
export function migrateLegacySpaceControl(node, serialized) {
  if (node.comfyClass !== 'ComfyUISpaceControl') return;
  if (legacyNodeTitles.has(node.title)) node.title = 'Space Control';
  const legacyOutputs = { '範囲': 'MASK', 'Region': 'MASK', '範囲プレビュー': 'Region preview' };
  for (const output of node.outputs ?? []) {
    if (Object.hasOwn(legacyOutputs, output.name)) output.name = legacyOutputs[output.name];
    if (output.type === 'MASK') output.name = 'MASK';
    if (output.name === 'MASK') output.localized_name = 'MASK';
  }
  const values = baseValues(serialized ?? {});
  if (!values) return;
  for (const widget of node.widgets ?? []) {
    const i = controlNames.indexOf(widget.name);
    if (i >= 0 && values[i] !== undefined) widget.value = values[i];
  }
}

/** Migrate controls and removed sockets before LiteGraph restores saved graphs. */
export function migrateSpaceControlWorkflow(graph) {
  for (const subgraph of graph.definitions?.subgraphs ?? []) migrateSpaceControlWorkflow(subgraph);
  const controls = (graph.nodes ?? []).filter(isSpaceControlNode);
  if (!controls.length) return;
  for (const node of controls) normalizeControlNames(node);
  const links = [
    ...(graph.links ?? []).map(raw => ({raw, floating: false})),
    ...(graph.floatingLinks ?? []).map(raw => ({raw, floating: true})),
  ].map(({raw, floating}) => Array.isArray(raw)
    ? {id: raw[0], origin_id: raw[1], origin_slot: raw[2], target_id: raw[3], target_slot: raw[4], type: raw[5], raw, floating}
    : {...raw, raw, floating});
  const byId = new Map(links.filter(link => !link.floating).map(link => [link.id, link]));
  const changes = new Map();
  for (const node of controls) {
    const inputs = node.inputs ?? [];
    const outputs = node.outputs ?? [];
    const newInputs = inputs.filter(input => !removedInputs.has(input.name));
    const modeSlot = newInputs.findIndex(input => input.name === 'space_mode');
    const colorSlot = newInputs.findIndex(input => input.name === 'color');
    if (colorSlot >= 0 && modeSlot > colorSlot) {
      [newInputs[colorSlot], newInputs[modeSlot]] = [newInputs[modeSlot], newInputs[colorSlot]];
    }
    const newOutputs = outputs.filter(output => output.type !== 'CONDITIONING' && output.type !== 'IMAGE');
    const inputSlots = inputs.map(input => newInputs.indexOf(input));
    const outputSlots = outputs.map(output => newOutputs.indexOf(output));
    const positive = byId.get(inputs.find(input => input.name === 'positive')?.link);
    changes.set(node.id, {inputSlots, outputSlots, positive, outputTypes: outputs.map(output => output.type)});
    node.inputs = newInputs;
    node.outputs = newOutputs;
    const values = baseValues(node);
    if (values) node.widgets_values = values;
    (node.properties ??= {}).space_control_layout = 2;
    if (node.widgets_values_named) {
      for (const name of removedInputs) delete node.widgets_values_named[name];
      if (values) node.widgets_values_named.position = values[0];
    }
    if (legacyNodeTitles.has(node.title)) node.title = 'Space Control';
    for (const output of node.outputs) {
      if (output.type === 'MASK' || output.name === '範囲' || output.name === 'Region') {
        output.name = 'MASK';
        output.localized_name = 'MASK';
      }
      if (output.name === '範囲プレビュー') output.name = 'Region preview';
    }
  }

  const kept = [];
  const keptFloating = [];
  const rewired = [];
  const removedPreviewTargets = new Set();
  for (const link of links) {
    const target = changes.get(link.target_id);
    if (target?.inputSlots[link.target_slot] === -1) continue;
    let source = link;
    const visited = new Set();
    while (changes.get(source.origin_id)?.outputSlots[source.origin_slot] === -1) {
      // Only the removed CONDITIONING output can bypass to its original prompt.
      if (changes.get(source.origin_id).outputTypes[source.origin_slot] !== 'CONDITIONING') {
        if (!link.floating) removedPreviewTargets.add(link.target_id);
        source = null; break;
      }
      if (visited.has(source.origin_id)) { source = null; break; }
      visited.add(source.origin_id);
      source = changes.get(source.origin_id).positive;
      if (!source) break;
    }
    if (!source) continue;
    const originSlot = changes.get(source.origin_id)?.outputSlots[source.origin_slot] ?? source.origin_slot;
    const targetSlot = target?.inputSlots[link.target_slot] ?? link.target_slot;
    const raw = link.raw;
    if (Array.isArray(raw)) {
      raw[1] = source.origin_id; raw[2] = originSlot; raw[4] = targetSlot;
    } else {
      raw.origin_id = source.origin_id; raw.origin_slot = originSlot; raw.target_slot = targetSlot;
      if (source !== link) delete raw.parentId;
    }
    if (source !== link && !link.floating) rewired.push({id: link.id, origin_id: source.origin_id, origin_slot: originSlot});
    (link.floating ? keptFloating : kept).push(raw);
  }
  graph.links = kept;
  if (graph.floatingLinks) graph.floatingLinks = keptFloating;
  const keptIds = new Set(kept.map(link => Array.isArray(link) ? link[0] : link.id));
  const rewiredIds = new Set(rewired.map(link => link.id));
  for (const node of graph.nodes ?? []) {
    for (const input of node.inputs ?? []) {
      if (input.link != null && !keptIds.has(input.link)) input.link = null;
    }
    for (const output of node.outputs ?? []) {
      if (output.links) output.links = output.links.filter(id => keptIds.has(id) && !rewiredIds.has(id));
    }
  }
  for (const input of graph.inputs ?? []) {
    if (input.linkIds) input.linkIds = input.linkIds.filter(id => keptIds.has(id) && !rewiredIds.has(id));
  }
  for (const link of rewired) {
    if (link.origin_id === -10) {
      const input = graph.inputs[link.origin_slot];
      (input.linkIds ??= []).push(link.id);
    } else {
      const node = graph.nodes.find(node => node.id === link.origin_id);
      (node.outputs[link.origin_slot].links ??= []).push(link.id);
    }
  }
  const floatingIds = new Set(keptFloating.map(link => Array.isArray(link) ? link[0] : link.id));
  for (const reroute of graph.reroutes ?? []) {
    reroute.linkIds = (reroute.linkIds ?? []).filter(id => (keptIds.has(id) || floatingIds.has(id)) && !rewiredIds.has(id));
  }
  // Dedicated old previews no longer need a separate output node. Keep saved-mask
  // nodes available for rewiring, but stop their missing input from invalidating a run.
  graph.nodes = (graph.nodes ?? []).filter(node => {
    if (!removedPreviewTargets.has(node.id) || node.inputs?.some(input => input.link != null)) return true;
    if (node.type === 'PreviewImage') return false;
    if (node.type === 'SaveImage') node.mode = 2;
    return true;
  });
}
