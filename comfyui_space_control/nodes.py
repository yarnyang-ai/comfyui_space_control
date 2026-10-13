"""ComfyUI node definition for Space Control."""

from __future__ import annotations

import torch

from comfy_api.latest import io, ui

from .space_control import (
    LEGACY_POSITIONS,
    SPACE_POSITIONS,
    build_space_mask,
    build_space_base,
    parse_color,
    release_mask,
    unit_value,
)


class SpaceControlNode(io.ComfyNode):
    """Prepare a spatial base to encourage open space before sampling."""

    @classmethod
    def validate_inputs(cls, position):
        """Accept legacy API positions without adding them to the visible choices."""
        # Linked positions are checked by build_space_mask when their values arrive.
        if position is None:
            return True
        if isinstance(position, str) and (position in SPACE_POSITIONS or position in LEGACY_POSITIONS):
            return True
        return "Unknown Space Control position."

    @classmethod
    def define_schema(cls):
        """Expose the node's connections and controls to ComfyUI."""
        return io.Schema(
            node_id="ComfyUISpaceControl",
            display_name="Space Control",
            category="conditioning/space_control",
            is_experimental=True,
            has_intermediate_output=True,
            description=(
                "Encourage open space in a selected image region using a solid color or noise."
            ),
            inputs=[
                io.Model.Input("model"),
                io.Vae.Input("vae"),
                io.Latent.Input("latent"),
                io.Combo.Input(
                    "position",
                    display_name="Position",
                    options=list(SPACE_POSITIONS),
                    default="top",
                ),
                io.Float.Input(
                    "width_ratio",
                    display_name="Width",
                    default=0.35,
                    min=0.01,
                    max=1.0,
                    step=0.01,
                ),
                io.Float.Input(
                    "strength",
                    display_name="Space strength",
                    default=0.4,
                    min=0.0,
                    max=1.0,
                    step=0.01,
                ),
                io.Combo.Input(
                    "space_mode",
                    display_name="Space mode",
                    options=["color", "rgb_noise", "latent_noise", "color_latent", "rgb_latent"],
                    default="color",
                    optional=True,
                    tooltip="Choose a solid color, colored-pixel noise, latent noise, or mix color or RGB with latent noise.",
                ),
                io.Color.Input("color", display_name="Color", default="#FFFFFF", optional=True),
                io.Int.Input(
                    "seed",
                    display_name="Seed",
                    default=0,
                    min=0,
                    max=0xFFFFFFFFFFFFFFFF,
                    optional=True,
                    tooltip="Makes noise and mixed bases reproducible. Ignored in color mode. Using the same integer as KSampler is fine; its random state is unchanged.",
                ),
            ],
            outputs=[
                io.Model.Output(),
                io.Latent.Output(),
                io.Mask.Output(),
            ],
        )

    @classmethod
    def execute(
        cls,
        model,
        vae,
        latent,
        position,
        width_ratio,
        strength,
        color="#FFFFFF",
        space_mode="color",
        seed=0,
    ):
        """Return MODEL, LATENT, MASK, and display the region inside the node.

        Input validation also runs when the base is disabled. Active bases
        modify copies of the model and latent.
        """
        strength = unit_value(strength, "strength")
        rgb = parse_color(color)
        if space_mode not in ("color", "rgb_noise", "latent_noise", "color_latent", "rgb_latent"):
            raise ValueError("Unknown Space Control mode.")
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 0xFFFFFFFFFFFFFFFF:
            raise ValueError("Space Control seed must be an integer from 0 to 2**64-1.")
        samples = latent.get("samples") if isinstance(latent, dict) else None
        if (
            not isinstance(samples, torch.Tensor)
            or samples.is_nested
            or samples.ndim not in (4, 5)
            or any(size < 1 for size in samples.shape)
        ):
            raise ValueError("Space Control needs a 4D image LATENT or 5D LATENT with one frame.")
        if samples.ndim == 5 and samples.shape[2] != 1:
            raise ValueError("Space Control supports images only, not video.")
        if not bool(torch.isfinite(samples).all()):
            raise ValueError("Space Control LATENT contains nonfinite values.")

        mask = build_space_mask(*samples.shape[-2:], position, width_ratio)
        if strength == 0:
            return io.NodeOutput(model, latent, mask, ui=ui.PreviewMask(mask))

        if "noise_mask" in latent or model.model_options.get("denoise_mask_function") is not None:
            # Replacing another mask or release hook would change its sampling behavior.
            raise ValueError(
                "Space Control cannot combine with an existing latent noise mask or denoise mask function. "
                "Use a separate model branch."
            )

        import comfy.sample

        # Model metadata may require different channels or spatial dimensions.
        samples = comfy.sample.fix_empty_latent_channels(
            model,
            samples,
            latent.get("downscale_ratio_spacial"),
            latent.get("downscale_ratio_temporal"),
        )
        # Rebuild after correction so the mask and base use the final dimensions.
        mask = build_space_mask(*samples.shape[-2:], position, width_ratio)
        latent_format = model.get_model_object("latent_format")
        sampling_samples = latent_format.process_in(samples)

        base = build_space_base(
            samples,
            sampling_samples,
            latent_format,
            vae,
            mode=space_mode,
            seed=seed,
            rgb=rgb,
        )

        # Image VAEs may include a singleton frame dimension; align it before blending.
        if base.ndim == 5 and samples.ndim == 4 and base.shape[2] == 1:
            base = base.squeeze(2)
        if base.ndim == 4 and samples.ndim == 5:
            base = base.unsqueeze(2)
        if base.shape[1:] != samples.shape[1:]:
            raise ValueError("VAE base and model LATENT shapes do not match. Check the VAE/model pairing.")
        base = base.expand(samples.shape[0], *base.shape[1:]).to(samples)
        spatial = mask.to(samples).reshape(
            1,
            1,
            *([1] if samples.ndim == 5 else []),
            *samples.shape[-2:],
        )

        # Empty latents are zero in sampling space, so preserve that baseline before mixing the base.
        baseline = samples
        if not bool(torch.count_nonzero(samples)):
            baseline = latent_format.process_out(torch.zeros_like(sampling_samples)).to(samples)
        weight = spatial * strength
        # Copies isolate the modified branch from other consumers of the same inputs.
        output_latent = dict(latent)
        output_latent["samples"] = baseline * (1 - weight) + base * weight
        # The latent mask and model hook form a pair; both outputs must reach the sampler.
        output_latent["noise_mask"] = 1 - strength * mask
        output_model = model.clone()
        output_model.set_model_denoise_mask_function(release_mask)

        return io.NodeOutput(output_model, output_latent, mask, ui=ui.PreviewMask(mask))


NODE_CLASS_MAPPINGS = {"ComfyUISpaceControl": SpaceControlNode}
NODE_DISPLAY_NAME_MAPPINGS = {"ComfyUISpaceControl": "Space Control"}
