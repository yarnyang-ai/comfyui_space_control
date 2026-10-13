"""Build source-free color and noise bases and release them during sampling."""
from __future__ import annotations
import math
import re
import torch

SPACE_POSITIONS = ('top', 'top_right', 'right', 'bottom_right', 'bottom',
                   'bottom_left', 'left', 'top_left', 'center', 'all_edges')
# Preserve region geometry for saved position names.
LEGACY_POSITIONS = {
    '上': 'top', '下': 'bottom', '左': 'left', '右': 'right',
    '左上': 'top_left', '右上': 'top_right',
    '左下': 'bottom_left', '右下': 'bottom_right',
    '中央': 'center', '全周': 'all_edges', 'perimeter': 'all_edges',
}


def unit_value(value, name, minimum=0.):
    """Validate a finite numeric value in [minimum, 1], rejecting booleans."""
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not minimum <= value <= 1.:
        raise ValueError(f'{name} must be between {minimum} and 1.')
    return float(value)


def parse_color(color):
    """Parse opaque hexadecimal RGB into three floats in [0, 1]."""
    if not isinstance(color,str) or re.fullmatch(r'#[0-9a-fA-F]{6}(?:FF|ff)?',color) is None:
        raise ValueError('Color must be opaque #RRGGBB (or #RRGGBBFF).')
    return tuple(int(color[i:i+2],16)/255 for i in (1,3,5))


def build_space_base(samples, sampling_samples, latent_format, vae, *, mode, seed, rgb):
    """Create a base from validated options, before latent shape alignment.

    Latent noise uses the model's sampling-space shape, which can differ from the
    input latent shape. A local CPU generator leaves global RNG state intact.
    """
    if mode in ("latent_noise", "color_latent", "rgb_latent"):
        generator = torch.Generator(device="cpu").manual_seed(seed)
        noise = torch.randn(
            sampling_samples.shape,
            generator=generator,
            dtype=torch.float32,
        ).to(sampling_samples)
        latent_noise = latent_format.process_out(noise)
        if mode == "latent_noise":
            return latent_noise

        image_mode = "color" if mode == "color_latent" else "rgb_noise"
        image_base = build_space_base(
            samples,
            sampling_samples,
            latent_format,
            vae,
            mode=image_mode,
            seed=seed,
            rgb=rgb,
        )
        if image_base.ndim == 5 and samples.ndim == 4 and image_base.shape[2] == 1:
            image_base = image_base.squeeze(2)
        if image_base.ndim == 4 and samples.ndim == 5:
            image_base = image_base.unsqueeze(2)
        if image_base.shape[1:] != samples.shape[1:]:
            raise ValueError("VAE base and model LATENT shapes do not match. Check the VAE/model pairing.")
        return (latent_noise.to(samples) + image_base.to(samples)) * 0.5

    scale = vae.spacial_compression_encode()
    if not isinstance(scale, int) or scale < 1:
        raise ValueError("Space Control needs an image VAE with integer spatial compression.")
    # Encode one RGB image, then let the caller broadcast it across the latent batch.
    shape = (1, samples.shape[-2] * scale, samples.shape[-1] * scale, 3)
    if mode == "rgb_noise":
        generator = torch.Generator(device="cpu").manual_seed(seed)
        pixels = torch.rand(shape, generator=generator, dtype=torch.float32)
    else:
        pixels = torch.tensor(rgb, dtype=torch.float32).reshape(1, 1, 1, 3).expand(shape).contiguous()
    return vae.encode(pixels)


def build_space_mask(height, width, position, fraction):
    """Return a feathered CPU mask [1, H, W] with 1 inside the chosen region.

    Distances use normalized image coordinates. Corner regions intersect the
    selected edges; center and all_edges distances are scaled by two.
    """
    fraction=unit_value(fraction,'width_ratio',.01)
    position = LEGACY_POSITIONS.get(position, position)
    if position not in SPACE_POSITIONS:
        raise ValueError('Unknown space position.')
    y,x=torch.meshgrid(torch.linspace(0.,1.,height),torch.linspace(0.,1.,width),indexing='ij')
    if position=='center': distance=2*torch.maximum((x-.5).abs(),(y-.5).abs())
    elif position=='all_edges': distance=2*torch.minimum(torch.minimum(x,1-x),torch.minimum(y,1-y))
    else:
        edges=[]
        if 'left' in position: edges.append(x)
        if 'right' in position: edges.append(1-x)
        if 'top' in position: edges.append(y)
        if 'bottom' in position: edges.append(1-y)
        distance=torch.stack(edges).amax(0)
    # Smoothstep softens the boundary over the outer quarter of the selected width.
    t=((fraction-distance)/max(fraction*.25,1e-6)).clamp(0,1)
    return (t*t*(3-2*t)).unsqueeze(0)


def release_mask(sigma, denoise_mask, extra_options):
    """Release the base by the cutoff at 30% of the scheduled step count.

    Interpolate smoothly in sigma space until the mask is fully open (1).
    Schedules with at most one sampling step are opened immediately.
    """
    sigmas=extra_options['sigmas']
    if len(sigmas)<=2:
        return torch.ones_like(denoise_mask)
    # Use the actual schedule supplied by the sampler, including partial denoising.
    cutoff=sigmas[max(1,math.ceil((len(sigmas)-1)*.3))]
    span=sigmas[0]-cutoff
    if float(span)<=0: return torch.ones_like(denoise_mask)
    weight=((sigma.reshape(-1)[0]-cutoff)/span).clamp(0,1)
    weight=weight*weight*(3-2*weight)
    return denoise_mask+(1-denoise_mask)*(1-weight.to(denoise_mask))
