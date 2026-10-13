"""ComfyUI extension entrypoint for Space Control."""

from typing_extensions import override

from comfy_api.latest import ComfyExtension, io

from .nodes import SpaceControlNode

# ComfyUI serves this directory as the extension's frontend assets.
WEB_DIRECTORY = './web'


class SpaceControlExtension(ComfyExtension):
    """Register the maintained Space Control node through the ComfyUI V3 API."""
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [SpaceControlNode]


async def comfy_entrypoint() -> SpaceControlExtension:
    """Return the extension instance discovered by ComfyUI."""
    return SpaceControlExtension()
