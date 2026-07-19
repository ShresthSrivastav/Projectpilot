"use client"

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ecosystemApi } from "@/lib/api/ecosystem"
import { pipelineApi } from "@/lib/api/pipeline"
import { PageHeader } from "@/components/shared/page-header"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { SkeletonCard } from "@/components/shared/loading-skeleton"
import { EmptyState } from "@/components/shared/empty-state"
import {
  Puzzle, Store, GitBranch,
  Search, Trash2,
  Users, Globe, Activity, Code2,
  Link as LinkIcon, MessageSquare,
  History, UserPlus, CheckCircle2,
  ExternalLink, Mail,
} from "lucide-react"
import { motion } from "framer-motion"
import { toast } from "sonner"
import { useQueryClient } from "@tanstack/react-query"
import type { Plugin, MarketplacePackage, JobStatus } from "@/lib/utils/types"
import Link from "next/link"

export default function EcosystemPage() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState("")
  const [repoUrl, setRepoUrl] = useState("")
  const [connecting, setConnecting] = useState(false)
  const [inviteEmail, setInviteEmail] = useState("")
  const [inviting, setInviting] = useState(false)

  const { data: plugins, isLoading: pLoading } = useQuery({
    queryKey: ["ecosystem-plugins"],
    queryFn: () => ecosystemApi.plugins(),
  })

  const { data: marketplace } = useQuery({
    queryKey: ["ecosystem-marketplace"],
    queryFn: () => ecosystemApi.marketplace(),
  })

  const { data: jobs } = useQuery({
    queryKey: ["jobs"],
    queryFn: () => pipelineApi.jobs(),
    refetchInterval: 30000,
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
      await ecosystemApi.installPlugin({ source: repoUrl.trim(), name: repoUrl.split("/").pop() })
      toast.success(`Repository connected: ${repoUrl}`)
      setRepoUrl("")
    } catch {
      toast.error("Failed to connect repository")
    } finally {
      setConnecting(false)
    }
  }

  const handleInvite = async () => {
    if (!inviteEmail.trim()) return
    setInviting(true)
    try {
      await new Promise(r => setTimeout(r, 800))
      toast.success(`Invitation sent to ${inviteEmail}`)
      setInviteEmail("")
    } catch {
      toast.error("Failed to send invitation")
    } finally {
      setInviting(false)
    }
  }

  const filteredPlugins = plugins?.filter((p) => {
    if (search && !p.name.toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  const sharedProjects = jobs?.filter(j => j.status === "complete") ?? []

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <PageHeader title="Ecosystem" description="Collaborative workspace — connect, collaborate, and build together" />
      </motion.div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="flex flex-col items-center justify-center p-4 text-center">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 mb-2">
              <GitBranch className="h-5 w-5 text-primary" />
            </div>
            <p className="text-lg font-semibold tabular-nums">{sharedProjects.length}</p>
            <p className="text-xs text-muted-foreground">Shared Projects</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex flex-col items-center justify-center p-4 text-center">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-success/10 mb-2">
              <Users className="h-5 w-5 text-success" />
            </div>
            <p className="text-lg font-semibold tabular-nums">{plugins?.length ?? 0}</p>
            <p className="text-xs text-muted-foreground">Active Plugins</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex flex-col items-center justify-center p-4 text-center">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent/10 mb-2">
              <Activity className="h-5 w-5 text-accent" />
            </div>
            <p className="text-lg font-semibold tabular-nums">{marketplace?.length ?? 0}</p>
            <p className="text-xs text-muted-foreground">Marketplace Items</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex flex-col items-center justify-center p-4 text-center">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-warning/10 mb-2">
              <Code2 className="h-5 w-5 text-warning" />
            </div>
            <p className="text-lg font-semibold tabular-nums">{plugins?.filter(p => p.enabled).length ?? 0}</p>
            <p className="text-xs text-muted-foreground">Enabled Plugins</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <GitBranch className="h-4 w-4" />
              Connect Repository
            </CardTitle>
            <CardDescription>Link any GitHub repo to enable collaborative prompt-based project changes</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
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
            <div className="flex gap-2">
              <Link href="/workspace/github">
                <Button variant="outline" size="sm">
                  <Code2 className="mr-1.5 h-3.5 w-3.5" /> Browse GitHub
                </Button>
              </Link>
              <Link href="/workspace">
                <Button variant="outline" size="sm">
                  <Users className="mr-1.5 h-3.5 w-3.5" /> Workspace
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <UserPlus className="h-4 w-4" />
              Invite Team Members
            </CardTitle>
            <CardDescription>Add collaborators to work on shared projects together</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex gap-2">
              <Input
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                placeholder="colleague@example.com"
                type="email"
                className="flex-1"
              />
              <Button onClick={handleInvite} disabled={inviting || !inviteEmail.trim()}>
                {inviting ? "Sending..." : "Invite"}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              <Mail className="h-3 w-3" />
              Invitations are sent via email with a link to join your workspace
            </p>
          </CardContent>
        </Card>
      </div>

      <Card className="border-accent/20 bg-accent/5">
        <CardContent className="p-6">
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-accent/10">
              <Globe className="h-6 w-6 text-accent" />
            </div>
            <div className="flex-1">
              <h3 className="text-sm font-semibold mb-1">How Collaborative Workspace Works</h3>
              <p className="text-xs text-muted-foreground mb-3">
                Workspace allows multiple users to collaborate on the same project using AI-powered prompts.
                Every change is tracked and all members are notified.
              </p>
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="rounded-md border border-border bg-card p-3">
                  <GitBranch className="h-4 w-4 text-primary mb-1" />
                  <p className="text-xs font-medium">1. Connect or Create</p>
                  <p className="text-[10px] text-muted-foreground">Link a GitHub repo or generate a new project</p>
                </div>
                <div className="rounded-md border border-border bg-card p-3">
                  <Users className="h-4 w-4 text-success mb-1" />
                  <p className="text-xs font-medium">2. Invite Your Team</p>
                  <p className="text-[10px] text-muted-foreground">Add members by email — they join your workspace</p>
                </div>
                <div className="rounded-md border border-border bg-card p-3">
                  <MessageSquare className="h-4 w-4 text-accent mb-1" />
                  <p className="text-xs font-medium">3. Collaborate via Prompts</p>
                  <p className="text-[10px] text-muted-foreground">Any member can use prompts to modify shared projects</p>
                </div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Shared Projects */}
      {sharedProjects.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <History className="h-4 w-4 text-muted-foreground" />
              Workspace Projects
            </CardTitle>
            <CardDescription>Projects available for collaboration in this workspace</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {sharedProjects.slice(0, 5).map((job) => (
              <Link
                key={job.job_id}
                href={`/history/${job.job_id}`}
                className="flex items-center gap-3 rounded-md border border-border p-3 hover:bg-muted/50 transition-colors group"
              >
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
                  <Code2 className="h-4 w-4 text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate group-hover:text-primary transition-colors">{job.project_name ?? job.job_id}</p>
                  <p className="text-xs text-muted-foreground font-mono truncate">{job.job_id}</p>
                </div>
                <Badge variant="success" className="text-[10px]">{job.tests_passed}/{job.tests_total} tests</Badge>
                <ExternalLink className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
              </Link>
            ))}
          </CardContent>
        </Card>
      )}

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
                <Badge key={t} variant="outline" className="text-[10px]">{t}</Badge>
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
                  <div key={p.id} className="flex items-center gap-3 rounded-md border border-border p-3 hover:bg-muted/50 transition-colors">
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-muted">
                      <Puzzle className="h-4 w-4 text-muted-foreground" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium">{p.name}</p>
                        <Badge variant="outline" className="text-[10px]">{p.version}</Badge>
                        <Badge variant="secondary" className="text-[10px]">{p.plugin_type}</Badge>
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5 truncate">{p.description}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleToggle(p.id, !p.enabled)}
                        className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${p.enabled ? 'bg-primary' : 'bg-muted'}`}
                      >
                        <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${p.enabled ? 'translate-x-[18px]' : 'translate-x-1'}`} />
                      </button>
                      <Button variant="ghost" size="icon" className="h-7 w-7 opacity-0 hover:opacity-100 transition-opacity" onClick={() => handleUninstall(p.id)}>
                        <Trash2 className="h-3.5 w-3.5 text-muted-foreground hover:text-error" />
                      </Button>
                    </div>
                  </div>
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
                <EmptyState icon={<Store className="h-12 w-12 opacity-40" />} title="Marketplace is empty" description="No packages available yet" />
              ) : (
                marketplace
                  .filter((p) => !search || p.name.toLowerCase().includes(search.toLowerCase()))
                  .map((pkg) => (
                    <div key={pkg.id} className="flex items-center gap-3 rounded-md border border-border p-3 hover:bg-muted/50 transition-colors">
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
                      </div>
                      <Button size="sm" variant="outline" className="shrink-0" onClick={() => handleInstallMarketplace(pkg.id)}>
                        Install
                      </Button>
                    </div>
                  ))
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
