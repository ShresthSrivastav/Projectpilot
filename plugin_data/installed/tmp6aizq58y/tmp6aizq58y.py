"""API Test Plugin"""
# name: api-plugin
# version: 1.0.0
from sdk.plugin_sdk.base_plugin import BasePlugin
class ApiPlugin(BasePlugin):
    def install(self) -> bool: return True
    def uninstall(self) -> bool: return True
    def configure(self, config) -> bool: return True
    def validate(self) -> bool: return True
