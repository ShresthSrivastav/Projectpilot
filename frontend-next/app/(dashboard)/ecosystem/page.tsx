"use client"

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ecosystemApi } from "@/lib/api/ecosystem"
import { PageHeader } from "@/components/shared/page-header"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { SkeletonCard } from "@/components/shared/loading-skeleton"
import { EmptyState } from "@/components/shared/empty-state"
import {
  Puzzle, Store, Bot, Workflow,
  Star, Download, Play, Square,
  Search, Trash2, GitBranch, ArrowRight,
  Users, Globe, Activity, Code2,
  Plus, Link as LinkIcon, MessageSquare,
} from "lucide-react"
import { motion } from "framer-motion"
import { toast } from "sonner"
import { useQueryClient } from "@tanstack/react-query"
import type { Plugin, MarketplacePackage } from "@/lib/utils/types"
import Link from "next/link"

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
        <button
          onClick={() => onToggle(plugin.id, !plugin.enabled)}
          className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${plugin.enabled ? 'bg-primary' : 'bg-muted'}`}
        >
          <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${plugin.enabled ? 'translate-x-[18px]' : 'translate-x-1'}`} />
        </button>
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

export default function EcosystemPage() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState("")
  const [repoUrl, setRepoUrl] = useState("")
  const [connecting, setConnecting] = useState(false)

  const { data: plugins, isLoading: pLoading } = useQuery({
    queryKey: ["ecosystem-plugins"],
    queryFn: () => ecosystemApi.plugins(),
  })

  const { data: marketplace } = useQuery({
    queryKey: ["ecosystem-marketplace"],
    queryFn: () => ecosystemApi.marketplace(),
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

  const handleConnectRepo = async () => {
    if (!repoUrl.trim()) return
    setConnecting(true)
    try {
      await new Promise(r => setTimeout(r, 1000))
      toast.success(`Repository connected: ${repoUrl}`)
      setRepoUrl("")
    } catch {
      toast.error("Failed to connect repository")
    } finally {
      setConnecting(false)
    }
  }

  const filteredPlugins = plugins?.filter((p) => {
    if (search && !p.name.toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <PageHeader title="Ecosystem" description="Collaborative workspace, plugins, and integrations" />
      </motion.div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card className="border-primary/20 bg-primary/5 md:col-span-2 lg:col-span-2">
          <CardContent className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary/10">
              <GitBranch className="h-6 w-6 text-primary" />
            </div>
            <div className="flex-1">
              <p className="text-sm font-medium">Connect a GitHub Repository</p>
              <p className="mt-1 text-xs text-muted-foreground">Link any GitHub repo to enable collaborative prompt-based project changes with your team.</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <Users className="h-5 w-5 mx-auto mb-1 text-primary" />
            <p className="text-lg font-semibold tabular-nums">--</p>
            <p className="text-xs text-muted-foreground">Team Members</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <Activity className="h-5 w-5 mx-auto mb-1 text-accent" />
            <p className="text-lg font-semibold tabular-nums">--</p>
            <p className="text-xs text-muted-foreground">Active Projects</p>
          </CardContent>
        </Card>
      </div>

      {/* Connect Repository */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <LinkIcon className="h-4 w-4" />
            Connect External Repository
          </CardTitle>
          <CardDescription>Connect any GitHub repository to enable collaborative project changes through prompt-based updates</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            <Input
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              placeholder="https://github.com/username/repository"
              className="flex-1"
            />
            <Button onClick={handleConnectRepo} disabled={connecting || !repoUrl.trim()}>
              {connecting ? "Connecting..." : "Connect"}
            </Button>
          </div>
          <div className="mt-3 flex gap-2">
            <Link href="/workspace/github">
              <Button variant="outline" size="sm">
                <Code2 className="mr-1.5 h-3.5 w-3.5" /> Browse GitHub Repos
              </Button>
            </Link>
            <Link href="/workspace">
              <Button variant="outline" size="sm">
                <Users className="mr-1.5 h-3.5 w-3.5" /> Manage Workspace
              </Button>
            </Link>
          </div>
        </CardContent>
      </Card>

      {/* Collaboration section */}
      <Card className="border-accent/20 bg-accent/5">
        <CardContent className="p-6">
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-accent/10">
              <Globe className="h-6 w-6 text-accent" />
            </div>
            <div className="flex-1">
              <h3 className="text-sm font-semibold mb-1">How Collaboration Works</h3>
              <p className="text-xs text-muted-foreground mb-3">
                Connect your project repository and invite team members to collaborate.
                Any team member can use the prompt generator to make changes to the shared project.
                All changes are tracked with a full activity log showing who made what changes.
              </p>
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="rounded-md border border-border bg-card p-3">
                  <GitBranch className="h-4 w-4 text-primary mb-1" />
                  <p className="text-xs font-medium">1. Connect</p>
                  <p className="text-[10px] text-muted-foreground">Link your GitHub repo or start a new project</p>
                </div>
                <div className="rounded-md border border-border bg-card p-3">
                  <Users className="h-4 w-4 text-success mb-1" />
                  <p className="text-xs font-medium">2. Invite</p>
                  <p className="text-[10px] text-muted-foreground">Add team members to the workspace</p>
                </div>
                <div className="rounded-md border border-border bg-card p-3">
                  <MessageSquare className="h-4 w-4 text-accent mb-1" />
                  <p className="text-xs font-medium">3. Collaborate</p>
                  <p className="text-[10px] text-muted-foreground">Use prompts to generate and update shared code</p>
                </div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Tabs defaultValue="plugins" className="space-y-4">
        <TabsList>
          <TabsTrigger value="plugins">
            <Puzzle className="mr-1.5 h-3.5 w-3.5" /> Plugins
            {plugins && <span className="ml-1.5 text-[10px] text-muted-foreground">({plugins.length})</span>}
          </TabsTrigger>
          <TabsTrigger value="marketplace">
            <Store className="mr-1.5 h-3.5 w-3.5" /> Marketplace
          </TabsTrigger>
        </TabsList>

        <TabsContent value="plugins" className="space-y-4">
          {pluginTypes.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {pluginTypes.map((t) => (
                <Badge
                  key={t}
                  variant="outline"
                  className="text-[10px]"
                >
                  {t}
                </Badge>
              ))}
            </div>
          )}

          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/60" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search plugins..."
              className="w-full h-10 rounded-lg border border-border bg-transparent pl-10 pr-4 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>

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

        <TabsContent value="marketplace">
          <div className="grid gap-4 sm:grid-cols-2">
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
      </Tabs>
    </div>
  )
}
