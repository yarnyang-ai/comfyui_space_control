"""Catch reversed directions, hard borders, stuck fill, and nonzero bypass."""
import sys
import os
import unittest
import tempfile
import numpy as np
from PIL import Image
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
comfyui_root = os.environ.get('COMFYUI_ROOT')
if comfyui_root:
    sys.path.insert(0, comfyui_root)
import torch
import folder_paths
from comfyui_space_control.space_control import build_space_mask, parse_color, release_mask
from comfyui_space_control.nodes import SpaceControlNode
from comfy.model_patcher import ModelPatcher
from comfy.latent_formats import SD15, Wan21, HunyuanImage21Refiner


class TinyColorEncoder:
    """Replace only the expensive VAE encode, keeping image/color inputs observable."""
    def __init__(self,channels=4): self.channels=channels
    def spacial_compression_encode(self): return 8
    def encode(self,pixels):
        self.pixels=pixels
        return torch.full((1,self.channels,pixels.shape[1]//8,pixels.shape[2]//8),2.)


class PixelEncoder(TinyColorEncoder):
    def encode(self,pixels):
        self.pixels=pixels
        return pixels.permute(0,3,1,2)[:, :1, ::8, ::8].expand(-1,self.channels,-1,-1).clone()


def tiny_model(format_=None):
    module=torch.nn.Module();module.latent_format=format_ or SD15()
    return ModelPatcher(module,torch.device('cpu'),torch.device('cpu'))


class SpaceControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preview_dir = tempfile.TemporaryDirectory()
        cls.previous_temp = folder_paths.get_temp_directory()
        folder_paths.set_temp_directory(cls.preview_dir.name)

    @classmethod
    def tearDownClass(cls):
        folder_paths.set_temp_directory(cls.previous_temp)
        cls.preview_dir.cleanup()

    def test_region_preview_is_inline_and_matches_the_returned_mask(self):
        for strength in [0., .4]:
            output = SpaceControlNode.execute(tiny_model(), TinyColorEncoder(),
                {'samples': torch.zeros(1, 4, 8, 16)}, 'right', .35, strength, '#FFFFFF')
            self.assertEqual(len(output.result), 3)
            image = output.ui.as_dict()['images'][0]
            self.assertEqual(image['type'], 'temp')
            with Image.open(Path(self.preview_dir.name) / image['subfolder'] / image['filename']) as png:
                self.assertEqual(png.size, (16, 8))
                expected = (output.result[2][0].numpy() * 255).astype(np.uint8)
                for channel in range(3):
                    np.testing.assert_array_equal(np.asarray(png)[:, :, channel], expected)

    def test_legacy_positions_preserve_the_same_regions(self):
        old=['上','下','左','右','左上','右上','左下','右下','中央','全周','perimeter']
        new=['top','bottom','left','right','top_left','top_right','bottom_left','bottom_right','center','all_edges','all_edges']
        for before, after in zip(old,new):
            self.assertTrue(torch.equal(build_space_mask(31,47,before,.35),build_space_mask(31,47,after,.35)))

    def test_cardinal_and_corner_masks_select_named_edges(self):
        for position, inside, outside in [
            ('top',(0,4),(8,4)), ('bottom',(8,4),(0,4)),
            ('left',(4,0),(4,8)), ('right',(4,8),(4,0)),
            ('top_left',(0,0),(0,8)), ('top_right',(0,8),(8,8)),
            ('bottom_left',(8,0),(0,0)), ('bottom_right',(8,8),(8,0)),
            ('center',(4,4),(0,0)), ('all_edges',(0,0),(4,4))]:
            with self.subTest(position=position):
                mask=build_space_mask(9,9,position,.4)[0]
                self.assertGreater(float(mask[inside]),.95)
                self.assertEqual(float(mask[outside]),0.)

    def test_width_increases_area_with_a_soft_transition(self):
        small=build_space_mask(40,100,'右',.2)
        big=build_space_mask(40,100,'右',.5)
        self.assertGreater(float(big.sum()),float(small.sum()))
        self.assertTrue(bool(((small>0)&(small<1)).any()))
        self.assertEqual(float(small[0,20,0]),0.)

    def test_color_is_rgb_and_invalid_or_transparent_input_is_rejected(self):
        self.assertEqual(parse_color('#FF8000'),(1.,128/255,0.))
        for color in ['white','#ffffff00','#GG0000','ffffff']:
            with self.assertRaises(ValueError): parse_color(color)

    def test_base_is_released_before_final_steps(self):
        mask=torch.tensor([[[[1.,.4]]]])
        sigmas=torch.tensor([1.,.8,.6,.4,.2,0.])
        early=release_mask(torch.tensor([1.]),mask,{'sigmas':sigmas})
        late=release_mask(torch.tensor([.2]),mask,{'sigmas':sigmas})
        self.assertTrue(torch.equal(early,mask))
        self.assertTrue(torch.equal(late,torch.ones_like(mask)))
        middle=release_mask(torch.tensor([.8]),mask,{'sigmas':sigmas})
        self.assertEqual(float(middle[0,0,0,0]),1.)
        self.assertGreater(float(middle[0,0,0,1]),.4)
        self.assertLess(float(middle[0,0,0,1]),1.)

    def test_strength_zero_does_not_encode_or_patch(self):
        model=object();vae=object()
        latent={'samples':torch.zeros(1,16,1,8,8)}
        result=SpaceControlNode.execute(model,vae,latent,'右上',.35,0.,'#FFFFFF').result
        self.assertIs(result[0],model)
        self.assertIs(result[1],latent)
        self.assertEqual(len(result),3)
        self.assertEqual(tuple(result[2].shape),(1,8,8))

    def test_invalid_parameters_fail_before_gpu_work(self):
        for position,width,strength,color in [('unknown',.3,.5,'#FFFFFF'),('右',0,.5,'#FFFFFF'),
            ('右',.3,1.1,'#FFFFFF'),('右',.3,.5,'#zzzzzz')]:
            with self.assertRaises(ValueError):
                SpaceControlNode.execute(object(),object(),{'samples':torch.zeros(1,4,8,8)},position,width,strength,color)

    def test_video_is_rejected_as_image_only(self):
        with self.assertRaises(ValueError):
            SpaceControlNode.execute(object(),object(),{'samples':torch.zeros(1,16,2,8,8)},'上',.3,.5,'#FFFFFF')

    def test_model_resolution_metadata_is_respected_before_vae_encoding(self):
        # A 16-pixel latent stride represents a 128px canvas here, not 64px.
        model=tiny_model();vae=TinyColorEncoder()
        latent={'samples':torch.zeros(1,4,8,8),'downscale_ratio_spacial':16}
        output=SpaceControlNode.execute(model,vae,latent,'右',.4,.6,'#FF8000').result
        self.assertEqual(tuple(vae.pixels.shape),(1,128,128,3))
        self.assertEqual(tuple(output[1]['samples'].shape),(1,4,16,16))
        self.assertTrue(torch.equal(vae.pixels[0,0,0],torch.tensor([1.,128/255,0.])))
        self.assertNotIn('denoise_mask_function',model.model_options)
        self.assertIn('denoise_mask_function',output[0].model_options)
        self.assertTrue(torch.equal(latent['samples'],torch.zeros(1,4,8,8)))

    def test_nonfinite_latent_is_rejected(self):
        with self.assertRaises(ValueError):
            SpaceControlNode.execute(tiny_model(),TinyColorEncoder(),{'samples':torch.full((1,4,8,8),float('nan'))},'右',.3,.5,'#FFFFFF')

    def test_initial_base_changes_gradually_with_positive_strength(self):
        model=tiny_model();latent={'samples':torch.zeros(1,4,8,8)}
        small=SpaceControlNode.execute(model,TinyColorEncoder(),latent,'右',.4,.2,'#FFFFFF').result[1]['samples']
        large=SpaceControlNode.execute(model,TinyColorEncoder(),latent,'右',.4,.4,'#FFFFFF').result[1]['samples']
        self.assertAlmostEqual(float(large[0,0,4,-1]),2*float(small[0,0,4,-1]),places=6)
        self.assertLess(float(small[0,0,4,-1]),2.)

    def test_empty_anima_background_remains_zero_in_sampling_space(self):
        format_=Wan21();model=tiny_model(format_)
        latent={'samples':torch.zeros(1,16,1,8,8)}
        result=SpaceControlNode.execute(model,TinyColorEncoder(16),latent,'右',.4,.5,'#FFFFFF').result[1]
        sampling_space=format_.process_in(result['samples'])
        self.assertTrue(torch.allclose(sampling_space[...,0],torch.zeros_like(sampling_space[...,0]),atol=1e-6))

    def test_single_step_never_keeps_fill_in_final_prediction(self):
        mask=torch.tensor([[[[.2,1.]]]])
        result=release_mask(torch.tensor([1.]),mask,{'sigmas':torch.tensor([1.,0.])})
        self.assertTrue(torch.equal(result,torch.ones_like(mask)))

    def test_latent_noise_is_seeded_in_model_space_without_vae_or_global_rng_changes(self):
        model=tiny_model(Wan21());latent={'samples':torch.zeros(1,16,1,8,8)}
        rng=torch.random.get_rng_state().clone()
        def run(seed):
            return SpaceControlNode.execute(model,object(),latent,'上',.35,.4,'#FFFFFF',
                space_mode='latent_noise',seed=seed).result[1]
        a,b,c=run(42),run(42),run(43)
        self.assertTrue(torch.equal(a['samples'],b['samples']))
        self.assertFalse(torch.equal(a['samples'],c['samples']))
        self.assertTrue(torch.equal(rng,torch.random.get_rng_state()))
        expected=torch.randn((1,16,1,8,8),generator=torch.Generator().manual_seed(42))
        expected*=build_space_mask(8,8,'上',.35).reshape(1,1,1,8,8)*.4
        self.assertTrue(torch.allclose(model.get_model_object('latent_format').process_in(a['samples']),expected,atol=1e-6))

    def test_rgb_noise_uses_reproducible_pixels_and_ignores_color(self):
        model=tiny_model();latent={'samples':torch.zeros(1,4,8,8)}
        def run(seed,color):
            vae=PixelEncoder()
            result=SpaceControlNode.execute(model,vae,latent,'右',.4,.4,color,
                space_mode='rgb_noise',seed=seed).result
            return result,vae.pixels
        a,pa=run(42,'#FFFFFF');b,pb=run(42,'#000000');c,pc=run(43,'#FFFFFF')
        self.assertTrue(torch.equal(pa,pb));self.assertTrue(torch.equal(a[1]['samples'],b[1]['samples']))
        self.assertFalse(torch.equal(pa,pc));self.assertFalse(torch.equal(a[1]['samples'],c[1]['samples']))
        self.assertGreater(float(pa.std()),.25)
        self.assertGreaterEqual(float(pa.min()),0.);self.assertLessEqual(float(pa.max()),1.)

    def test_invalid_new_controls_are_rejected(self):
        for kwargs in [dict(space_mode='bad'),dict(seed=-1),dict(seed=True),dict(seed=1.5),
            dict(seed=2**64)]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                SpaceControlNode.execute(object(),object(),{'samples':torch.zeros(1,4,8,8)},'上',.35,0.,'#FFFFFF',**kwargs)

    def test_shape_changing_latent_format_uses_its_sampling_space_shape(self):
        fmt=HunyuanImage21Refiner();model=tiny_model(fmt)
        samples=torch.zeros(1,64,1,8,8)
        output=SpaceControlNode.execute(model,object(),{'samples':samples},'上',.35,.4,'#FFFFFF',
            space_mode='latent_noise',seed=42).result[1]['samples']
        expected=fmt.process_out(torch.randn(fmt.process_in(samples).shape,generator=torch.Generator().manual_seed(42)))
        expected*=build_space_mask(8,8,'上',.35).reshape(1,1,1,8,8)*.4
        self.assertEqual(output.shape,samples.shape)
        self.assertTrue(torch.allclose(output,expected))

    def test_noise_base_preserves_nonempty_half_batch_outside_mask(self):
        model=tiny_model();samples=torch.full((2,4,8,8),.5,dtype=torch.float16)
        output=SpaceControlNode.execute(model,object(),{'samples':samples},'上',.35,.4,'#FFFFFF',
            space_mode='latent_noise',seed=42).result[1]['samples']
        self.assertEqual(output.dtype,samples.dtype)
        self.assertTrue(torch.equal(output[:,:,-1,:],samples[:,:,-1,:]))
        self.assertFalse(torch.equal(output[0,:,0,:],output[1,:,0,:]))
        self.assertTrue(torch.equal(samples,torch.full_like(samples,.5)))


if __name__=='__main__': unittest.main()
