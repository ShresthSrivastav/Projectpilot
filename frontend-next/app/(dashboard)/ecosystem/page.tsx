"use client"

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ecosystemApi } from "@/lib/api/ecosystem"
import { PageHeader } from "@/components/shared/page-header"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { SkeletonCard } from "@/components/shared/loading-skeleton"
import { EmptyState } from "@/components/shared/empty-state"
import {
  Puzzle, Store, Bot, Workflow,
  Star, Download, Play, Square,
  Search, Trash2,
} from "lucide-react"
import { motion } from "framer-motion"
import { toast } from "sonner"
import { useQueryClient } from "@tanstack/react-query"
import type { Plugin, MarketplacePackage } from "@/lib/utils/types"

// ───── Plugin Card ─────
function PluginCard({ plugin, onToggle, onUninstall }: {
  plugin: Plugin
  onToggle: (id: string, enabled: boolean) => void
  onUninstall: (id: string) => void
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-center gap-3 rounded-md border border-border p-3 hover:bg-muted/50 transition-colors"
    >
      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-muted">
        <Puzzle className="h-4 w-4 text-muted-foreground" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium">{plugin.name}</p>
          <Badge variant="outline" className="text-[10px]">{plugin.version}</Badge>
          <Badge variant="secondary" className="text-[10px]">{plugin.plugin_type}</Badge>
        </div>
        <p className="text-xs text-muted-foreground mt-0.5 truncate">{plugin.description}</p>
      </div>
      <div className="flex items-center gap-2">
        <Switch checked={plugin.enabled} onCheckedChange={(v) => onToggle(plugin.id, v)} />
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 opacity-0 hover:opacity-100 transition-opacity"
          onClick={() => onUninstall(plugin.id)}
        >
          <Trash2 className="h-3.5 w-3.5 text-muted-foreground hover:text-error" />
        </Button>
      </div>
    </motion.div>
  )
}

// ───── Marketplace Card ─────
function MarketplaceCard({ pkg, onInstall }: {
  pkg: MarketplacePackage
  onInstall: (id: string) => void
}) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex items-center gap-3 rounded-md border border-border p-3 hover:bg-muted/50 transition-colors"
    >
      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/10">
        <Store className="h-4 w-4 text-accent" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium">{pkg.name}</p>
          <Badge variant="outline" className="text-[10px]">v{pkg.version}</Badge>
          <span className="text-[10px] text-muted-foreground">by {pkg.author}</span>
        </div>
        <p className="text-xs text-muted-foreground mt-0.5 truncate">{pkg.description}</p>
        <div className="flex items-center gap-3 mt-1">
          <div className="flex items-center gap-1">
            <Star className="h-3 w-3 text-warning fill-warning" />
            <span className="text-[10px] text-muted-foreground">{pkg.rating.toFixed(1)}</span>
          </div>
          <span className="text-[10px] text-muted-foreground">{pkg.downloads.toLocaleString()} downloads</span>
          <Badge variant="secondary" className="text-[10px]">{pkg.package_type}</Badge>
        </div>
      </div>
      <Button size="sm" variant="outline" className="shrink-0" onClick={() => onInstall(pkg.id)}>
        <Download className="mr-1 h-3.5 w-3.5" /> Install
      </Button>
    </motion.div>
  )
}

// ───── Agent Card ─────
function AgentCard({ agent, onDelete }: {
  agent: Record<string, unknown>
  onDelete: (id: string) => void
}) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex items-center gap-3 rounded-md border border-border p-3 hover:bg-muted/50 transition-colors"
    >
      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10">
        <Bot className="h-4 w-4 text-primary" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium">{agent.name as string}</p>
          <Badge
            variant={(agent.status as string) === "active" ? "success" : "secondary"}
            className="text-[10px]"
          >
            {(agent.status as string) ?? "inactive"}
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground mt-0.5">{agent.description as string}</p>
      </div>
      <div className="flex items-center gap-1">
        {(agent.status as string) === "active" ? (
          <Button size="sm" variant="outline" className="h-7 text-xs">
            <Square className="mr-1 h-3 w-3" /> Stop
          </Button>
        ) : (
          <Button size="sm" variant="outline" className="h-7 text-xs">
            <Play className="mr-1 h-3 w-3" /> Run
          </Button>
        )}
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={() => onDelete(agent.id as string)}
        >
          <Trash2 className="h-3.5 w-3.5 text-muted-foreground hover:text-error" />
        </Button>
      </div>
    </motion.div>
  )
}

// ───── Workflow Card ─────
function WorkflowCard({ workflow, onRun, onDelete }: {
  workflow: Record<string, unknown>
  onRun: (id: string) => void
  onDelete: (id: string) => void
}) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex items-center gap-3 rounded-md border border-border p-3 hover:bg-muted/50 transition-colors"
    >
      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-success/10">
        <Workflow className="h-4 w-4 text-success" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium">{workflow.name as string}</p>
        <p className="text-xs text-muted-foreground mt-0.5">{workflow.description as string}</p>
        {(workflow.trigger_type as string) && (
          <Badge variant="outline" className="text-[10px] mt-1">
            Trigger: {(workflow.trigger_type as string)}
          </Badge>
        )}
      </div>
      <div className="flex items-center gap-1">
        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => onRun(workflow.id as string)}>
          <Play className="mr-1 h-3 w-3" /> Run
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={() => onDelete(workflow.id as string)}
        >
          <Trash2 className="h-3.5 w-3.5 text-muted-foreground hover:text-error" />
        </Button>
      </div>
    </motion.div>
  )
}

// ───── Main Page ─────
export default function EcosystemPage() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState("")
  const [filterType, setFilterType] = useState<string>("")

  const { data: plugins, isLoading: pLoading } = useQuery({
    queryKey: ["ecosystem-plugins"],
    queryFn: () => ecosystemApi.plugins(),
  })

  const { data: marketplace } = useQuery({
    queryKey: ["ecosystem-marketplace"],
    queryFn: () => ecosystemApi.marketplace(),
  })

  const { data: agents } = useQuery({
    queryKey: ["ecosystem-agents"],
    queryFn: () => ecosystemApi.agents(),
  })

  const { data: workflows } = useQuery({
    queryKey: ["ecosystem-workflows"],
    queryFn: () => ecosystemApi.workflows(),
  })

  const filteredPlugins = plugins?.filter((p) => {
    if (search && !p.name.toLowerCase().includes(search.toLowerCase())) return false
    if (filterType && p.plugin_type !== filterType) return false
    return true
  })



  const pluginTypes = [...new Set(plugins?.map((p) => p.plugin_type) ?? [])]

  const handleToggle = async (id: string, enabled: boolean) => {
    try {
      if (enabled) {
        await ecosystemApi.enablePlugin(id)
      } else {
        await ecosystemApi.disablePlugin(id)
      }
      queryClient.invalidateQueries({ queryKey: ["ecosystem-plugins"] })
      toast.success(enabled ? "Plugin enabled" : "Plugin disabled")
    } catch {
      toast.error("Failed to toggle plugin")
    }
  }

  const handleUninstall = async (id: string) => {
    try {
      await ecosystemApi.uninstallPlugin(id)
      queryClient.invalidateQueries({ queryKey: ["ecosystem-plugins"] })
      toast.success("Plugin uninstalled")
    } catch {
      toast.error("Failed to uninstall plugin")
    }
  }

  const handleInstallMarketplace = async (pkgId: string) => {
    try {
      await ecosystemApi.installMarketplace({ package_id: pkgId })
      queryClient.invalidateQueries({ queryKey: ["ecosystem-marketplace"] })
      queryClient.invalidateQueries({ queryKey: ["ecosystem-plugins"] })
      toast.success("Package installed")
    } catch {
      toast.error("Failed to install package")
    }
  }

  const handleDeleteAgent = async (id: string) => {
    try {
      await ecosystemApi.deleteAgent(id)
      queryClient.invalidateQueries({ queryKey: ["ecosystem-agents"] })
      toast.success("Agent deleted")
    } catch {
      toast.error("Failed to delete agent")
    }
  }

  const handleDeleteWorkflow = async (id: string) => {
    try {
      await ecosystemApi.deleteWorkflow(id)
      queryClient.invalidateQueries({ queryKey: ["ecosystem-workflows"] })
      toast.success("Workflow deleted")
    } catch {
      toast.error("Failed to delete workflow")
    }
  }

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <PageHeader title="Ecosystem" description="Plugins, agents, and workflows" />
      </motion.div>

      {/* Search bar */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/60" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search ecosystem..."
          className="w-full h-10 rounded-lg border border-border bg-transparent pl-10 pr-4 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-ring"
        />
      </div>

      <Tabs defaultValue="plugins" className="space-y-4">
        <TabsList>
          <TabsTrigger value="plugins">
            <Puzzle className="mr-1.5 h-3.5 w-3.5" /> Plugins
            {plugins && <span className="ml-1.5 text-[10px] text-muted-foreground">({plugins.length})</span>}
          </TabsTrigger>
          <TabsTrigger value="marketplace">
            <Store className="mr-1.5 h-3.5 w-3.5" /> Marketplace
          </TabsTrigger>
          <TabsTrigger value="agents">
            <Bot className="mr-1.5 h-3.5 w-3.5" /> Agents
            {agents && <span className="ml-1.5 text-[10px] text-muted-foreground">({(agents as unknown[]).length})</span>}
          </TabsTrigger>
          <TabsTrigger value="workflows">
            <Workflow className="mr-1.5 h-3.5 w-3.5" /> Workflows
            {workflows && <span className="ml-1.5 text-[10px] text-muted-foreground">({(workflows as unknown[]).length})</span>}
          </TabsTrigger>
        </TabsList>

        {/* ─── Plugins Tab ─── */}
        <TabsContent value="plugins" className="space-y-4">
          {/* Type filter */}
          {pluginTypes.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              <Badge
                variant={!filterType ? "default" : "outline"}
                className="cursor-pointer text-[10px]"
                onClick={() => setFilterType("")}
              >
                All
              </Badge>
              {pluginTypes.map((t) => (
                <Badge
                  key={t}
                  variant={filterType === t ? "default" : "outline"}
                  className="cursor-pointer text-[10px]"
                  onClick={() => setFilterType(t)}
                >
                  {t}
                </Badge>
              ))}
            </div>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Installed Plugins</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {pLoading ? (
                <SkeletonCard count={4} />
              ) : !filteredPlugins || filteredPlugins.length === 0 ? (
                <EmptyState
                  icon={<Puzzle className="h-12 w-12 opacity-40" />}
                  title={search ? "No matching plugins" : "No plugins installed"}
                  description="Browse the marketplace to find and install plugins"
                />
              ) : (
                filteredPlugins.map((p) => (
                  <PluginCard
                    key={p.id}
                    plugin={p}
                    onToggle={handleToggle}
                    onUninstall={handleUninstall}
                  />
                ))
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ─── Marketplace Tab ─── */}
        <TabsContent value="marketplace">
          <div className="grid gap-4 sm:grid-cols-2">
            {/* Stats */}
            <Card>
              <CardContent className="p-4 text-center">
                <p className="text-2xl font-semibold tabular-nums">{marketplace?.length ?? 0}</p>
                <p className="text-xs text-muted-foreground">Available Packages</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4 text-center">
                <p className="text-2xl font-semibold tabular-nums text-accent">
                  {marketplace?.reduce((s, p) => s + p.downloads, 0).toLocaleString() ?? 0}
                </p>
                <p className="text-xs text-muted-foreground">Total Downloads</p>
              </CardContent>
            </Card>
          </div>

          <Card className="mt-4">
            <CardHeader>
              <CardTitle className="text-sm font-medium">Available Packages</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {!marketplace || marketplace.length === 0 ? (
                <EmptyState
                  icon={<Store className="h-12 w-12 opacity-40" />}
                  title="Marketplace is empty"
                  description="No packages available yet"
                />
              ) : (
                marketplace
                  .filter((p) => !search || p.name.toLowerCase().includes(search.toLowerCase()))
                  .map((pkg) => (
                    <MarketplaceCard
                      key={pkg.id}
                      pkg={pkg}
                      onInstall={handleInstallMarketplace}
                    />
                  ))
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ─── Agents Tab ─── */}
        <TabsContent value="agents">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Custom Agents</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {!agents || (agents as unknown[]).length === 0 ? (
                <EmptyState
                  icon={<Bot className="h-12 w-12 opacity-40" />}
                  title="No custom agents"
                  description="Create custom agents to automate specific tasks"
                  action={{ label: "Create Agent", onClick: () => {} }}
                />
              ) : (
                (agents as unknown[]).map((a, i) => {
                  const agent = a as Record<string, unknown>
                  return (
                    <AgentCard
                      key={(agent.id as string) ?? i}
                      agent={agent}
                      onDelete={handleDeleteAgent}
                    />
                  )
                })
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ─── Workflows Tab ─── */}
        <TabsContent value="workflows">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Workflows</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {!workflows || (workflows as unknown[]).length === 0 ? (
                <EmptyState
                  icon={<Workflow className="h-12 w-12 opacity-40" />}
                  title="No workflows"
                  description="Create automated workflows to chain agents and actions"
                  action={{ label: "Create Workflow", onClick: () => {} }}
                />
              ) : (
                (workflows as unknown[]).map((w, i) => {
                  const workflow = w as Record<string, unknown>
                  return (
                    <WorkflowCard
                      key={(workflow.id as string) ?? i}
                      workflow={workflow}
                      onRun={(id) => toast.success(`Running workflow ${id}`)}
                      onDelete={handleDeleteWorkflow}
                    />
                  )
                })
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
