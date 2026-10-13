"""ComfyUI entrypoint for an installation of the complete repository."""

from .comfyui_space_control import comfy_entrypoint

# Resolve frontend assets relative to this installed repository, not its name.
WEB_DIRECTORY = "./comfyui_space_control/web"

# Keep the V3 entrypoint; exporting legacy mappings would bypass the V3 loader.
__all__ = ["comfy_entrypoint", "WEB_DIRECTORY"]
