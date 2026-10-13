import test from 'node:test';
import assert from 'node:assert/strict';
import * as compat from '../comfyui_space_control/web/color_compat.mjs';
const { removeDuplicateColorWidgets, migrateLegacySpaceControl } = compat;

test('renames saved node and API controls while preserving values and seed links', () => {
  const graph = {nodes: [{id: 17, type: 'ComfyUISpaceLegacy', title: 'Space Legacy',
    inputs: ['model', 'vae', 'latent', 'position', 'width_ratio', 'strength', 'old_mode', 'color', 'old_seed']
      .map(name => ({name, widget: {name}, link: name === 'old_seed' ? 1 : null})),
    outputs: [{name: 'MODEL', type: 'MODEL'}, {name: 'LATENT', type: 'LATENT'}, {name: 'Region', type: 'MASK'}],
    properties: {space_legacy_layout: 2, 'Node name for S&R': 'ComfyUISpaceLegacy'},
    widgets_values: ['right', .35, .8, 'rgb_latent', '#112233', 42],
    widgets_values_named: {position: 'right', width_ratio: .35, strength: .8, old_mode: 'rgb_latent', color: '#112233', old_seed: 42}},
    {id: 2, type: 'PrimitiveInt', outputs: [{type: 'INT', links: [1]}]}],
    links: [[1, 2, 0, 17, 8, 'INT']]};
  compat.migrateSpaceControlWorkflow(graph);
  const control = graph.nodes[0];
  assert.equal(control.type, 'ComfyUISpaceControl');
  assert.equal(control.title, 'Space Control');
  assert.equal(control.properties['Node name for S&R'], 'ComfyUISpaceControl');
  assert.equal(control.properties.space_control_layout, 2);
  assert.equal(Object.hasOwn(control.properties, 'space_legacy_layout'), false);
  assert.deepEqual(control.inputs.map(input => input.name), ['model','vae','latent','position','width_ratio','strength','space_mode','color','seed']);
  assert.equal(control.inputs[6].widget.name, 'space_mode');
  assert.equal(control.inputs[8].widget.name, 'seed');
  assert.equal(control.inputs[8].link, 1);
  assert.deepEqual(control.widgets_values, ['right', .35, .8, 'rgb_latent', '#112233', 42]);
  assert.equal(control.widgets_values_named.space_mode, 'rgb_latent');
  assert.equal(control.widgets_values_named.seed, 42);
  assert.equal(Object.hasOwn(control.widgets_values_named, 'old_mode'), false);
  assert.equal(Object.hasOwn(control.widgets_values_named, 'old_seed'), false);
  assert.deepEqual(graph.links, [[1, 2, 0, 17, 8, 'INT']]);
  assert.equal(control.outputs[2].name, 'MASK');
  compat.migrateSpaceControlWorkflow(graph);
  assert.equal(control.widgets_values_named.seed, 42);
});

test('saved Japanese positions become English without changing newer controls', () => {
  for (const [oldValue, newValue] of [['上', 'top'], ['右', 'right'], ['左下', 'bottom_left'], ['中央', 'center'], ['全周', 'all_edges'], ['perimeter', 'all_edges']]) {
    for (const length of [5, 8]) {
      const values = [oldValue, .35, .4, '#FFFFFF', '', 'latent_noise', 42, 1.6].slice(0, length);
      const node = {comfyClass: 'ComfyUISpaceControl', widgets: [{name: 'position', value: oldValue}]};
      migrateLegacySpaceControl(node, {widgets_values: values});
      assert.equal(node.widgets[0].value, newValue);
    }
  }
});

test('saved default titles and output labels become English, preserving custom titles', () => {
  const node = {comfyClass: 'ComfyUISpaceControl', title: 'Space Control / 余白の下地', outputs: [{name: '範囲'}, {name: '範囲プレビュー'}]};
  migrateLegacySpaceControl(node, {});
  assert.equal(node.title, 'Space Control');
  assert.deepEqual(node.outputs.map(output => output.name), ['MASK', 'Region preview']);
  node.title = 'Space Control';
  migrateLegacySpaceControl(node, {});
  assert.equal(node.title, 'Space Control');
  node.title = 'Sky region';
  migrateLegacySpaceControl(node, {});
  assert.equal(node.title, 'Sky region');
});

test('keeps the native color and other inputs when a legacy extension appends another picker', () => {
  const native={name:'color',type:'color',value:'#dceeff'};
  const contents={name:'contents',value:'balloon'};
  const node={comfyClass:'ComfyUISpaceControl',widgets:[native,contents,{name:'color',type:'COLOR',value:'#ffffff'}]};
  removeDuplicateColorWidgets(node);
  assert.deepEqual(node.widgets,[native,contents]);
  assert.equal(node.widgets[0].value,'#dceeff');
  removeDuplicateColorWidgets(node);
  assert.equal(node.widgets.length,2);
});

test('does not change widgets belonging to another extension', () => {
  const node={comfyClass:'OtherNode',widgets:[{name:'color'},{name:'color'}]};
  removeDuplicateColorWidgets(node);
  assert.equal(node.widgets.length,2);
});

test('old five-widget graphs default to color with seed zero', () => {
  for (const strength of [0, .2, .7]) {
    const widgets=[{name:'space_mode',value:'latent_noise'},{name:'seed',value:123}];
    const node={comfyClass:'ComfyUISpaceControl',widgets};
    migrateLegacySpaceControl(node,{widgets_values:['右',.35,strength,'#FFFFFF','balloon']});
    assert.deepEqual(widgets.map(w=>w.value),['color',0]);
  }
});

test('old object controls do not shift the restored mode or seed', () => {
  const node={comfyClass:'ComfyUISpaceControl',widgets:[{name:'space_mode',value:'balloon'},{name:'seed',value:'latent_noise'}]};
  migrateLegacySpaceControl(node,{widgets_values:['上',.35,0,'#FFFFFF','balloon','latent_noise',42,1.6]});
  assert.deepEqual(node.widgets.map(w=>w.value),['latent_noise',42]);
});

function legacyGraph(objectLinks = false) {
  const links = [
    [1,1,0,17,0,'MODEL'], [2,1,1,17,1,'VAE'], [3,1,2,17,2,'CLIP'],
    [4,1,3,17,3,'LATENT'], [5,1,4,17,4,'CONDITIONING'],
    [6,17,0,2,0,'MODEL'], [7,17,1,2,1,'LATENT'], [8,17,2,2,2,'CONDITIONING'],
    [9,17,3,2,3,'MASK'], [10,17,4,2,4,'IMAGE'], [11,1,5,17,5,'INT'],
  ];
  return {
    nodes: [
      {id:1,type:'Sources',outputs:['MODEL','VAE','CLIP','LATENT','CONDITIONING','INT'].map((type,i)=>({name:type,type,links:[i<5?i+1:11]}))},
      {id:17,type:'ComfyUISpaceControl',inputs:['model','vae','clip','latent','positive','seed'].map((name,i)=>({name,type:['MODEL','VAE','CLIP','LATENT','CONDITIONING','INT'][i],link:i<5?i+1:11})),
        outputs:['MODEL','LATENT','CONDITIONING','MASK','IMAGE'].map((type,i)=>({name:type,type,links:[i+6]})),
        widgets_values:['右',.35,1,'#090077','walking cat','rgb_noise',42,10],
        widgets_values_named:{position:'右',width_ratio:.35,strength:1,color:'#090077',contents:'walking cat',space_mode:'rgb_noise',seed:42,contents_strength:10}},
      {id:2,type:'Consumers',inputs:['MODEL','LATENT','CONDITIONING','MASK','IMAGE'].map((type,i)=>({name:type,type,link:i+6}))},
    ],
    links: objectLinks ? links.map(([id,origin_id,origin_slot,target_id,target_slot,type])=>({id,origin_id,origin_slot,target_id,target_slot,type})) : links,
  };
}

test('old workflows preserve prompt, latent, seed and mask while removing preview links', () => {
  const graph=legacyGraph();
  compat.migrateSpaceControlWorkflow(graph);
  const base=graph.nodes[1];
  assert.deepEqual(base.widgets_values,['right',.35,1,'rgb_noise','#090077',42]);
  assert.deepEqual(base.inputs.map(i=>i.name),['model','vae','latent','seed']);
  assert.deepEqual(base.outputs.map(o=>o.type),['MODEL','LATENT','MASK']);
  assert.deepEqual(graph.links,[
    [1,1,0,17,0,'MODEL'], [2,1,1,17,1,'VAE'], [4,1,3,17,2,'LATENT'],
    [6,17,0,2,0,'MODEL'], [7,17,1,2,1,'LATENT'], [8,1,4,2,2,'CONDITIONING'],
    [9,17,2,2,3,'MASK'], [11,1,5,17,3,'INT'],
  ]);
  assert.deepEqual(graph.nodes[0].outputs[2].links,[]);
  assert.deepEqual(graph.nodes[0].outputs[4].links,[8]);
  assert.equal(Object.hasOwn(base.widgets_values_named,'contents'),false);
  const once=structuredClone(graph);
  compat.migrateSpaceControlWorkflow(graph);
  assert.deepEqual(graph,once);
});

test('subgraphs with object links migrate without altering unrelated graphs', () => {
  const subgraph=legacyGraph(true);
  const workflow={nodes:[],links:[],definitions:{subgraphs:[subgraph]}};
  compat.migrateSpaceControlWorkflow(workflow);
  assert.deepEqual(subgraph.links.find(l=>l.id===8),{id:8,origin_id:1,origin_slot:4,target_id:2,target_slot:2,type:'CONDITIONING'});
  assert.equal(subgraph.links.some(l=>l.id===10),false);
  assert.equal(subgraph.nodes[2].inputs[4].link,null);
  const other={nodes:[{id:1,type:'OtherNode',widgets_values:['balloon']}],links:[]};
  const before=structuredClone(other);
  compat.migrateSpaceControlWorkflow(other);
  assert.deepEqual(other,before);
});

test('a subgraph prompt supplied through its boundary keeps the new direct link', () => {
  const graph=legacyGraph(true);
  const positive=graph.links.find(link=>link.id===5);
  positive.origin_id=-10; positive.origin_slot=0;
  graph.nodes[0].outputs[4].links=[];
  graph.inputs=[{name:'positive',type:'CONDITIONING',linkIds:[5]}];
  compat.migrateSpaceControlWorkflow(graph);
  assert.deepEqual(graph.inputs[0].linkIds,[8]);
  assert.deepEqual(graph.links.find(link=>link.id===8),{id:8,origin_id:-10,origin_slot:0,target_id:2,target_slot:2,type:'CONDITIONING'});
});

test('chained old bases bypass all removed positive sockets', () => {
  const graph=legacyGraph();
  const second=structuredClone(graph.nodes[1]);
  second.id=18;
  for (const input of second.inputs) input.link=null;
  second.inputs[4].link=8;
  for (const output of second.outputs) output.links=[];
  second.outputs[2].links=[12];
  graph.links.find(link=>link[0]===8)[3]=18;
  graph.links.find(link=>link[0]===8)[4]=4;
  graph.links.push([12,18,2,2,2,'CONDITIONING']);
  graph.nodes[2].inputs[2].link=12;
  graph.nodes.push(second);
  compat.migrateSpaceControlWorkflow(graph);
  assert.deepEqual(graph.links.find(link=>link[0]===12),[12,1,4,2,2,'CONDITIONING']);
  assert.deepEqual(graph.nodes[0].outputs[4].links,[12]);
  assert.equal(graph.links.some(link=>link[0]===8),false);
});

test('unfinished connections keep the correct sockets and discard removed inputs', () => {
  const graph=legacyGraph(true);
  graph.floatingLinks=[
    {id:21,origin_id:17,origin_slot:3,target_id:-1,target_slot:-1,type:'MASK'},
    {id:22,origin_id:17,origin_slot:4,target_id:-1,target_slot:-1,type:'IMAGE'},
    {id:23,origin_id:-1,origin_slot:-1,target_id:17,target_slot:3,type:'LATENT'},
    {id:24,origin_id:-1,origin_slot:-1,target_id:17,target_slot:2,type:'CLIP'},
    {id:25,origin_id:17,origin_slot:2,target_id:-1,target_slot:-1,type:'CONDITIONING'},
  ];
  compat.migrateSpaceControlWorkflow(graph);
  assert.deepEqual(graph.floatingLinks,[
    {id:21,origin_id:17,origin_slot:2,target_id:-1,target_slot:-1,type:'MASK'},
    {id:23,origin_id:-1,origin_slot:-1,target_id:17,target_slot:2,type:'LATENT'},
    {id:25,origin_id:1,origin_slot:4,target_id:-1,target_slot:-1,type:'CONDITIONING'},
  ]);
  const once=structuredClone(graph);
  compat.migrateSpaceControlWorkflow(graph);
  assert.deepEqual(graph,once);
});


test('mode moves above color without changing settings or converted widget connections', () => {
  const graph = {
    nodes: [
      {id:1,type:'Sources',outputs:[{type:'COLOR',links:[1]},{type:'COMBO',links:[2]}]},
      {id:17,type:'ComfyUISpaceControl',inputs:['model','vae','latent','position','width_ratio','strength','color','space_mode','seed'].map((name,i)=>({name,link:i===6?1:i===7?2:null})),
        outputs:[{type:'MODEL',links:[]},{type:'LATENT',links:[]},{type:'MASK',links:[]},{type:'IMAGE',links:[3]}],
        widgets_values:['right',.25,.7,'#012345','rgb_latent',123]},
      {id:2,type:'PreviewImage',inputs:[{name:'images',link:3}]},
    ],
    links:[[1,1,0,17,6,'COLOR'],[2,1,1,17,7,'COMBO'],[3,17,3,2,0,'IMAGE']],
  };
  compat.migrateSpaceControlWorkflow(graph);
  const base=graph.nodes[1];
  assert.deepEqual(base.inputs.map(i=>i.name),['model','vae','latent','position','width_ratio','strength','space_mode','color','seed']);
  assert.deepEqual(base.widgets_values,['right',.25,.7,'rgb_latent','#012345',123]);
  assert.deepEqual(graph.links,[[1,1,0,17,7,'COLOR'],[2,1,1,17,6,'COMBO']]);
  assert.equal(graph.nodes.some(n=>n.id===2),false);
  const once=structuredClone(graph);
  compat.migrateSpaceControlWorkflow(graph);
  assert.deepEqual(graph,once);
  const node={comfyClass:'ComfyUISpaceControl',widgets:[{name:'color'},{name:'space_mode'},{name:'seed'}]};
  compat.migrateLegacySpaceControl(node,base);
  assert.deepEqual(node.widgets.map(w=>w.value),['#012345','rgb_latent',123]);
});

test('removed image output disables its old save node and leaves unrelated previews alone', () => {
  const graph={
    nodes:[
      {id:1,type:'ComfyUISpaceControl',outputs:[{type:'MODEL'},{type:'LATENT'},{type:'MASK'},{type:'IMAGE',links:[1]}]},
      {id:2,type:'SaveImage',mode:0,inputs:[{name:'images',type:'IMAGE',link:1}]},
      {id:3,type:'PreviewImage',mode:0,inputs:[{name:'images',type:'IMAGE',link:null}]},
    ],
    links:[[1,1,3,2,0,'IMAGE']],
  };
  compat.migrateSpaceControlWorkflow(graph);
  assert.equal(graph.nodes.find(n=>n.id===2).mode,2);
  assert.equal(graph.nodes.find(n=>n.id===3).mode,0);
});
