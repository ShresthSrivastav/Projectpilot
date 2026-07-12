import { apiGet, apiPost } from "./client"
import type { Plugin, MarketplacePackage } from "@/lib/utils/types"

export const ecosystemApi = {
  plugins: (params?: { plugin_type?: string; enabled_only?: boolean }) =>
    apiGet<Plugin[]>("/plugins", params as Record<string, unknown>),

  installPlugin: (data: { source: string; name?: string; version?: string }) =>
    apiPost<Plugin>("/plugins/install", data),

  uninstallPlugin: (pluginId: string) =>
    apiPost<{ message: string }>("/plugins/uninstall", { plugin_id: pluginId }),

  enablePlugin: (pluginId: string) =>
    apiPost<{ message: string }>("/plugins/enable", { plugin_id: pluginId }),

  disablePlugin: (pluginId: string) =>
    apiPost<{ message: string }>("/plugins/disable", { plugin_id: pluginId }),

  marketplace: (params?: { query?: string; package_type?: string; tag?: string; sort_by?: string; limit?: number }) =>
    apiGet<MarketplacePackage[]>("/plugins/marketplace", params as Record<string, unknown>),

  marketplaceList: (params?: { package_type?: string; verified_only?: boolean }) =>
    apiGet<MarketplacePackage[]>("/plugins/marketplace/list", params as Record<string, unknown>),

  installMarketplace: (data: { package_id: string }) =>
    apiPost<Plugin>("/plugins/marketplace/install", data),

  publishPackage: (data: { name: string; description: string; package_type: string; source: string }) =>
    apiPost<{ message: string }>("/plugins/marketplace/publish", data),

  health: () => apiGet<Record<string, unknown>>("/plugins/ecosystem/health"),

  agents: () => apiGet<Record<string, unknown>[]>("/plugins/agents/custom"),

  registerAgent: (data: { name: string; description: string; source: string }) =>
    apiPost<{ message: string }>("/plugins/agents/register", data),

  deleteAgent: (agentId: string) =>
    apiPost<{ message: string }>("/plugins/agents/delete", { agent_id: agentId }),

  workflows: () => apiGet<Record<string, unknown>[]>("/plugins/workflows"),

  registerWorkflow: (data: { name: string; description: string; steps: unknown[] }) =>
    apiPost<{ message: string }>("/plugins/workflows/register", data),

  deleteWorkflow: (workflowId: string) =>
    apiPost<{ message: string }>("/plugins/workflows/delete", { workflow_id: workflowId }),
}
