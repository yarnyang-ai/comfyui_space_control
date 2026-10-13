"""Catch bypassed bases and mismatched sampler inputs."""
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/'examples'

class SpaceControlWorkflowTests(unittest.TestCase):
    def test_one_integer_seed_feeds_base_and_each_sampler(self):
        for suffix in ['t2i_anima', 'i2i_anima']:
            w=json.loads((ROOT/f'space_control_{suffix}.json').read_text(encoding='utf-8'))
            nodes={n['id']:n for n in w['nodes']}
            base=next(n for n in nodes.values() if n['type']=='ComfyUISpaceControl')
            seed_slot=next(i for i, socket in enumerate(base['inputs']) if socket['name']=='seed')
            incoming={(l[3],l[4]):(l[1],l[2]) for l in w['links']}
            source=incoming[base['id'],seed_slot]
            self.assertEqual(nodes[source[0]]['type'],'PrimitiveInt')
            expected_seed=1234
            self.assertEqual(nodes[source[0]]['widgets_values'][0],expected_seed)
            self.assertFalse(any(n['type']=='RandomNoise' for n in nodes.values()))
            for sampler in (n for n in nodes.values() if n['type']=='KSampler'):
                seed_slot=next(i for i, socket in enumerate(sampler['inputs']) if socket['name']=='seed')
                self.assertEqual(incoming[sampler['id'],seed_slot],source)
            for graph in w.get('definitions', {}).get('subgraphs', []):
                seed_slot=next(i for i, socket in enumerate(graph['inputs']) if socket['name']=='seed')
                self.assertEqual(graph['inputs'][seed_slot]['type'],'INT')
                for sampler in (n for n in nodes.values() if n['type']==graph['id']):
                    self.assertEqual(incoming[sampler['id'],seed_slot],source)
                noise=next(n for n in graph['nodes'] if n['type']=='RandomNoise')
                advanced=next(n for n in graph['nodes'] if n['type']=='SamplerCustomAdvanced')
                links={l['id']:l for l in graph['links']}
                seed_link=links[noise['inputs'][0]['link']]
                self.assertEqual((seed_link['origin_id'],seed_link['origin_slot'],seed_link['type']),(-10,seed_slot,'INT'))
                noise_link=links[advanced['inputs'][0]['link']]
                self.assertEqual((noise_link['origin_id'],noise_link['origin_slot'],noise_link['type']),(noise['id'],0,'NOISE'))

    def test_space_control_widget_order_and_saved_defaults(self):
        for suffix in ['t2i_anima','i2i_anima']:
            w=json.loads((ROOT/f'space_control_{suffix}.json').read_text(encoding='utf-8'))
            node=next(n for n in w['nodes'] if n['type']=='ComfyUISpaceControl')
            controls=[i['name'] for i in node['inputs'] if 'widget' in i]
            self.assertEqual([output['type'] for output in node['outputs']], ['MODEL','LATENT','MASK'])
            self.assertEqual(controls,['position','width_ratio','strength','space_mode','color','seed'])
            strength=.8
            self.assertEqual(node['widgets_values'],['right',.35,strength,'color','#FFFFFF',8675309])
    def test_color_has_serialized_widget_binding_for_frontend_roundtrip(self):
        w=json.loads((ROOT/'space_control_t2i_anima.json').read_text(encoding='utf-8'))
        node=next(n for n in w['nodes'] if n['type']=='ComfyUISpaceControl')
        bindings=[i for i in node['inputs'] if i['name']=='color']
        self.assertEqual(len(bindings),1)
        self.assertEqual(bindings[0]['widget']['name'],'color')
        self.assertEqual(bindings[0]['type'],'COLOR')
    def test_single_uses_one_sampler_and_all_links_have_matching_sockets(self):
        for suffix,count in [('t2i_anima',1),('i2i_anima',1)]:
            w=json.loads((ROOT/f'space_control_{suffix}.json').read_text(encoding='utf-8'))
            nodes={n['id']:n for n in w['nodes']}
            for node in nodes.values():
                self.assertTrue(node.get('title', '').isascii())
            graphs=w.get('definitions', {}).get('subgraphs', [])
            sampler=graphs[0]['id'] if graphs else 'KSampler'
            self.assertEqual(sum(n['type']==sampler for n in nodes.values()),count)
            for id_,source,ss,target,ts,kind in w['links']:
                self.assertIn(id_,nodes[source]['outputs'][ss]['links'])
                self.assertEqual(nodes[target]['inputs'][ts]['link'],id_)
                self.assertEqual(nodes[source]['outputs'][ss]['type'],kind)
                self.assertEqual(nodes[target]['inputs'][ts]['type'],kind)
            for graph in graphs:
                internal={n['id']:n for n in graph['nodes']}
                for link in graph['links']:
                    id_=link['id']; source=link['origin_id']; target=link['target_id']
                    ss=link['origin_slot']; ts=link['target_slot']; kind=link['type']
                    if source==-10:
                        self.assertIn(id_,graph['inputs'][ss]['linkIds'])
                        self.assertEqual(graph['inputs'][ss]['type'],kind)
                    else:
                        self.assertIn(id_,internal[source]['outputs'][ss]['links'])
                        self.assertEqual(internal[source]['outputs'][ss]['type'],kind)
                    if target==-20:
                        self.assertIn(id_,graph['outputs'][ts]['linkIds'])
                        self.assertEqual(graph['outputs'][ts]['type'],kind)
                    else:
                        self.assertEqual(internal[target]['inputs'][ts]['link'],id_)
                        self.assertEqual(internal[target]['inputs'][ts]['type'],kind)

    def assert_ksampler_space_connections(self, suffix):
        w=json.loads((ROOT/f'space_control_{suffix}.json').read_text(encoding='utf-8'))
        self.assertFalse(w.get('definitions', {}).get('subgraphs', []))
        nodes={n['id']:n for n in w['nodes']}
        incoming={(l[3],l[4]):(l[1],l[2]) for l in w['links']}
        sampler=next(n for n in nodes.values() if n['type']=='KSampler')
        base=next(n for n in nodes.values() if n['type']=='ComfyUISpaceControl')
        decode=next(n for n in nodes.values() if n['type']=='VAEDecode')
        save=next(n for n in nodes.values() if n['type']=='SaveImage')
        def source(node, name):
            slot=next(i for i, socket in enumerate(node['inputs']) if socket['name']==name)
            return incoming[node['id'],slot]
        self.assertEqual(source(sampler,'model'),(base['id'],0))
        self.assertEqual(source(sampler,'latent_image'),(base['id'],1))
        self.assertEqual(source(decode,'samples'),(sampler['id'],0))
        self.assertEqual(source(decode,'vae'),source(base,'vae'))
        self.assertEqual(source(save,'images'),(decode['id'],0))
        positive=nodes[source(sampler,'positive')[0]]
        negative=nodes[source(sampler,'negative')[0]]
        self.assertEqual(positive['type'],'CLIPTextEncode')
        self.assertEqual(negative['type'],'CLIPTextEncode')
        return w, nodes, sampler, base, positive, source

    def test_t2i_uses_ksampler_with_paired_space_outputs_and_vae_decode(self):
        w,nodes,sampler,base,positive,source=self.assert_ksampler_space_connections('t2i_anima')
        self.assertTrue(positive['widgets_values'][0].startswith(
            'masterpiece, best quality,\nscore_9, score_8, score_7,\nsafe,\n1girl,'))
        self.assertEqual(positive['widgets_values_named']['text'],positive['widgets_values'][0])
        self.assertEqual(sampler['widgets_values'],[8675309,'fixed',25,5.5,'euler_ancestral','beta',1])
        for name,value in zip(['seed','control_after_generate','steps','cfg','sampler_name','scheduler','denoise'],sampler['widgets_values']):
            self.assertEqual(sampler['widgets_values_named'][name],value)

    def test_i2i_encodes_input_before_space_control_and_keeps_partial_denoise(self):
        w,nodes,sampler,base,positive,source=self.assert_ksampler_space_connections('i2i_anima')
        encode=nodes[source(base,'latent')[0]]
        self.assertEqual(encode['type'],'VAEEncode')
        image=nodes[source(encode,'pixels')[0]]
        self.assertEqual(image['type'],'LoadImage')
        self.assertEqual(source(encode,'vae'),source(base,'vae'))
        self.assertEqual(sampler['widgets_values'],[8675309,'fixed',25,5.5,'euler_ancestral','beta',.7])
        for name,value in zip(['seed','control_after_generate','steps','cfg','sampler_name','scheduler','denoise'],sampler['widgets_values']):
            self.assertEqual(sampler['widgets_values_named'][name],value)

if __name__=='__main__': unittest.main()
