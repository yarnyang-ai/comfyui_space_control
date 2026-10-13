import importlib.util
import os
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
if os.environ.get("COMFYUI_ROOT"):
    sys.path.insert(0, os.environ["COMFYUI_ROOT"])

from comfy_api.latest import ComfyExtension
from comfyui_space_control import comfy_entrypoint
from comfyui_space_control.nodes import NODE_CLASS_MAPPINGS, SpaceControlNode


class SpaceControlNodeTests(unittest.TestCase):
    def test_api_positions_accept_legacy_values_without_exposing_them_in_ui(self):
        for value in ['top', 'bottom_right', 'all_edges', 'perimeter', '上', '右下', '全周', None]:
            self.assertIs(SpaceControlNode.validate_inputs(position=value), True)
        for value in ['unknown', '', 42]:
            self.assertIsInstance(SpaceControlNode.validate_inputs(position=value), str)

    def test_node_ui_is_english_and_describes_user_actions(self):
        schema = SpaceControlNode.define_schema()
        self.assertEqual(schema.display_name, "Space Control")
        inputs = {item.id: item for item in schema.inputs}
        self.assertEqual(inputs["position"].default, "top")
        self.assertEqual(inputs["space_mode"].display_name, "Space mode")
        self.assertEqual(inputs["strength"].display_name, "Space strength")
        for item in [schema, *schema.inputs, *schema.outputs]:
            for attribute in ("display_name", "description", "tooltip"):
                value = getattr(item, attribute, None)
                if value:
                    self.assertTrue(value.isascii(), value)
        self.assertTrue(all(value.isascii() for value in inputs["position"].options))
        self.assertIn('all_edges', inputs['position'].options)
        self.assertNotIn('perimeter', inputs['position'].options)

    def test_repository_root_loads_under_an_arbitrary_install_name(self):
        # Manager installs the repository root under a name it chooses.
        entrypoint = PROJECT_ROOT / "__init__.py"
        self.assertTrue(entrypoint.is_file(), "The installed repository needs a root entrypoint.")
        module_name = "_space_control_install_test"
        spec = importlib.util.spec_from_file_location(module_name, entrypoint)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
            # A legacy mapping would make ComfyUI skip its V3 extension loader.
            self.assertFalse(hasattr(module, "NODE_CLASS_MAPPINGS"))
            extension = _complete_immediate_coroutine(module.comfy_entrypoint())
            self.assertIsInstance(extension, ComfyExtension)
            self.assertEqual(awaitable_node_ids(extension), {"ComfyUISpaceControl"})
            web = PROJECT_ROOT / module.WEB_DIRECTORY
            self.assertTrue((web / "space_control_color.js").is_file())
            self.assertTrue((web / "color_compat.mjs").is_file())
        finally:
            for name in list(sys.modules):
                if name == module_name or name.startswith(module_name + "."):
                    del sys.modules[name]

    def test_schema_exposes_current_space_control_controls(self):
        schema = SpaceControlNode.define_schema()
        self.assertEqual(schema.node_id, "ComfyUISpaceControl")
        self.assertLess([i.id for i in schema.inputs].index("space_mode"), [i.id for i in schema.inputs].index("color"))
        ui_order = [name for names in schema.get_v1_info(SpaceControlNode).input_order.values() for name in names]
        self.assertLess(ui_order.index("space_mode"), ui_order.index("color"))
        self.assertTrue(schema.has_intermediate_output)
        inputs = {item.id: item for item in schema.inputs}
        self.assertEqual(inputs["position"].get_io_type(), "COMBO")
        self.assertEqual(inputs["width_ratio"].default, 0.35)
        self.assertEqual(inputs["strength"].default, 0.4)
        self.assertEqual(inputs["color"].get_io_type(), "COLOR")
        self.assertEqual(inputs["space_mode"].options, ["color", "rgb_noise", "latent_noise", "color_latent", "rgb_latent"])
        self.assertEqual(set(inputs), {
            "model", "vae", "latent", "position", "width_ratio", "strength",
            "color", "space_mode", "seed",
        })
        self.assertEqual([item.get_io_type() for item in schema.outputs], [
            "MODEL", "LATENT", "MASK",
        ])

    def test_only_space_control_is_exported_and_registered(self):
        self.assertEqual(NODE_CLASS_MAPPINGS, {"ComfyUISpaceControl": SpaceControlNode})
        extension = _complete_immediate_coroutine(comfy_entrypoint())
        self.assertIsInstance(extension, ComfyExtension)
        self.assertEqual(awaitable_node_ids(extension), {"ComfyUISpaceControl"})


def awaitable_node_ids(extension):
    nodes = _complete_immediate_coroutine(extension.get_node_list())
    return {node.define_schema().node_id for node in nodes}


def _complete_immediate_coroutine(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as completed:
        return completed.value
    coroutine.close()
    raise AssertionError("The extension entrypoint and node list should not await external work.")


if __name__ == "__main__":
    unittest.main()
