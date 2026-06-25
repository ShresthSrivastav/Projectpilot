"""Test Plugin"""
# name: test-plugin
# version: 1.0.0
# author: Test
# description: A test plugin
# type: tool

from sdk.plugin_sdk.base_plugin import BasePlugin, PluginManifest

class TestPlugin(BasePlugin):
    def __init__(self, config=None):
        super().__init__(config)
        self.manifest = PluginManifest(name="test-plugin", version="1.0.0")
    def install(self) -> bool: return True
    def uninstall(self) -> bool: return True
    def configure(self, config) -> bool: return True
    def validate(self) -> bool: return True
