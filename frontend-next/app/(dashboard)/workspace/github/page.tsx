"use client"

import { useState } from "react"
import { PageHeader } from "@/components/shared/page-header"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { EmptyState } from "@/components/shared/empty-state"
import { SkeletonCard } from "@/components/shared/loading-skeleton"
import { GitHubConnectDialog } from "@/components/github/github-connect-dialog"
import { RepoCard } from "@/components/github/repo-card"
import { useQuery } from "@tanstack/react-query"
import { githubApi } from "@/lib/api/github"
import {
  GitBranch, GitPullRequest, Bug, FileCode, Folder,
  ExternalLink, ChevronRight,
} from "lucide-react"
import type { GitHubRepo } from "@/lib/utils/types"
import { motion } from "framer-motion"

export default function GitHubPage() {
  const { data: connections } = useQuery({
    queryKey: ["github-connections"],
    queryFn: () => githubApi.connections(),
  })

  const [selectedRepo, setSelectedRepo] = useState<GitHubRepo | null>(null)
  const [repoSearch, setRepoSearch] = useState("")
  const activeUsername = connections?.[0]?.username

  const { data: repos, isLoading: reposLoading } = useQuery({
    queryKey: ["github-repos", activeUsername],
    queryFn: () => githubApi.repos(activeUsername!),
    enabled: !!activeUsername,
  })

  const { data: branches } = useQuery({
    queryKey: ["github-branches", selectedRepo?.full_name],
    queryFn: () => githubApi.branches(selectedRepo!.full_name),
    enabled: !!selectedRepo,
  })

  const { data: pulls } = useQuery({
    queryKey: ["github-pulls", selectedRepo?.full_name],
    queryFn: () => githubApi.pulls(selectedRepo!.full_name),
    enabled: !!selectedRepo,
  })

  const { data: issues } = useQuery({
    queryKey: ["github-issues", selectedRepo?.full_name],
    queryFn: () => githubApi.issues(selectedRepo!.full_name),
    enabled: !!selectedRepo,
  })

  const { data: files } = useQuery({
    queryKey: ["github-files", selectedRepo?.full_name],
    queryFn: () => githubApi.files(selectedRepo!.full_name),
    enabled: !!selectedRepo,
  })

  const filteredRepos = repos?.filter((r) =>
    r.full_name.toLowerCase().includes(repoSearch.toLowerCase())
  )

  if (!connections || connections.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader title="GitHub Integration" description="Connect your GitHub repositories" />
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Connected Accounts</CardTitle>
          </CardHeader>
          <CardContent>
            <EmptyState
              icon={<GitBranch className="h-12 w-12 opacity-40" />}
              title="No GitHub accounts connected"
              description="Connect your GitHub to manage repos, PRs, and issues directly from ProjectPilot"
              action={{ label: "Connect GitHub", onClick: () => {} }}
            />
            <div className="mt-4 flex justify-center">
              <GitHubConnectDialog />
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader title="GitHub Integration" description={`Connected as ${activeUsername}`}>
        <GitHubConnectDialog />
      </PageHeader>

      {selectedRepo ? (
        <>
          {/* Repo header */}
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-center gap-3"
          >
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSelectedRepo(null)}
            >
              <ChevronRight className="mr-1 h-4 w-4 rotate-180" /> Back
            </Button>
            <GitBranch className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium">{selectedRepo.full_name}</span>
            <a
              href={selectedRepo.html_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-muted-foreground hover:text-foreground"
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          </motion.div>

          <Tabs defaultValue="files" className="space-y-4">
            <TabsList>
              <TabsTrigger value="files">
                <FileCode className="mr-1.5 h-3.5 w-3.5" /> Files
              </TabsTrigger>
              <TabsTrigger value="branches">
                <GitBranch className="mr-1.5 h-3.5 w-3.5" /> Branches
                {branches && (
                  <span className="ml-1.5 text-[10px] text-muted-foreground">({branches.length})</span>
                )}
              </TabsTrigger>
              <TabsTrigger value="pulls">
                <GitPullRequest className="mr-1.5 h-3.5 w-3.5" /> Pull Requests
                {pulls && (
                  <span className="ml-1.5 text-[10px] text-muted-foreground">({pulls.length})</span>
                )}
              </TabsTrigger>
              <TabsTrigger value="issues">
                <Bug className="mr-1.5 h-3.5 w-3.5" /> Issues
                {issues && (
                  <span className="ml-1.5 text-[10px] text-muted-foreground">({issues.length})</span>
                )}
              </TabsTrigger>
            </TabsList>

            <TabsContent value="files">
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm font-medium">File Browser</CardTitle>
                </CardHeader>
                <CardContent>
                  {!files || files.length === 0 ? (
                    <EmptyState
                      icon={<Folder className="h-10 w-10 opacity-40" />}
                      title="No files"
                      description="This repository appears to be empty"
                    />
                  ) : (
                    <div className="space-y-0.5">
                      {files.map((file, i) => (
                        <motion.div
                          key={file.path}
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          transition={{ delay: i * 0.02 }}
                          className="flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm hover:bg-muted cursor-pointer transition-colors"
                        >
                          {file.type === "dir" ? (
                            <Folder className="h-4 w-4 text-accent shrink-0" />
                          ) : (
                            <FileCode className="h-4 w-4 text-muted-foreground shrink-0" />
                          )}
                          <span className="font-mono text-xs">{file.name}</span>
                        </motion.div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="branches">
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm font-medium">Branches</CardTitle>
                </CardHeader>
                <CardContent>
                  {!branches || branches.length === 0 ? (
                    <EmptyState
                      icon={<GitBranch className="h-10 w-10 opacity-40" />}
                      title="No branches"
                      description="No branches found in this repository"
                    />
                  ) : (
                    <div className="space-y-1">
                      {branches.map((branch, i) => (
                        <motion.div
                          key={branch.name}
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          transition={{ delay: i * 0.03 }}
                          className="flex items-center gap-3 rounded-md px-3 py-2 text-sm hover:bg-muted transition-colors"
                        >
                          <GitBranch className="h-4 w-4 text-muted-foreground shrink-0" />
                          <span className="font-mono text-xs">{branch.name}</span>
                          <span className="ml-auto text-[10px] text-muted-foreground/60 font-mono">
                            {branch.commit.sha.substring(0, 7)}
                          </span>
                        </motion.div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="pulls">
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm font-medium">Pull Requests</CardTitle>
                </CardHeader>
                <CardContent>
                  {!pulls || pulls.length === 0 ? (
                    <EmptyState
                      icon={<GitPullRequest className="h-10 w-10 opacity-40" />}
                      title="No pull requests"
                      description="No open pull requests in this repository"
                    />
                  ) : (
                    <div className="space-y-1">
                      {pulls.map((pr, i) => (
                        <motion.div
                          key={pr.number}
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          transition={{ delay: i * 0.03 }}
                          className="flex items-center gap-3 rounded-md px-3 py-2.5 text-sm hover:bg-muted transition-colors"
                        >
                          <GitPullRequest className="h-4 w-4 text-success shrink-0" />
                          <div className="flex-1 min-w-0">
                            <span className="font-medium truncate">{pr.title}</span>
                            <p className="text-xs text-muted-foreground">
                              #{pr.number} by {pr.user?.login}
                            </p>
                          </div>
                          <Badge
                            variant={pr.state === "open" ? "success" : "secondary"}
                            className="text-[10px] capitalize"
                          >
                            {pr.state}
                          </Badge>
                        </motion.div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="issues">
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm font-medium">Issues</CardTitle>
                </CardHeader>
                <CardContent>
                  {!issues || issues.length === 0 ? (
                    <EmptyState
                      icon={<Bug className="h-10 w-10 opacity-40" />}
                      title="No issues"
                      description="No open issues in this repository"
                    />
                  ) : (
                    <div className="space-y-1">
                      {issues.map((issue, i) => (
                        <motion.div
                          key={issue.number}
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          transition={{ delay: i * 0.03 }}
                          className="flex items-center gap-3 rounded-md px-3 py-2.5 text-sm hover:bg-muted transition-colors"
                        >
                          <Bug className="h-4 w-4 text-warning shrink-0" />
                          <div className="flex-1 min-w-0">
                            <span className="font-medium truncate">{issue.title}</span>
                            <p className="text-xs text-muted-foreground">#{issue.number}</p>
                          </div>
                          <Badge
                            variant={issue.state === "open" ? "success" : "secondary"}
                            className="text-[10px] capitalize"
                          >
                            {issue.state}
                          </Badge>
                        </motion.div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </>
      ) : (
        /* Repository list */
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <GitBranch className="h-4 w-4 text-muted-foreground" />
              Repositories
            </CardTitle>
            <div className="relative mt-2">
              <input
                value={repoSearch}
                onChange={(e) => setRepoSearch(e.target.value)}
                placeholder="Search repositories..."
                className="w-full h-9 rounded-md border border-border bg-transparent pl-3 pr-3 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-ring"
              />
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {reposLoading ? (
              <SkeletonCard count={5} />
            ) : !filteredRepos || filteredRepos.length === 0 ? (
              <EmptyState
                icon={<GitBranch className="h-12 w-12 opacity-40" />}
                title={repoSearch ? "No matching repos" : "No repositories found"}
                description={
                  repoSearch
                    ? "Try a different search term"
                    : "Connect a GitHub account to see your repositories"
                }
              />
            ) : (
              filteredRepos.map((repo, i) => (
                <motion.div
                  key={repo.full_name}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.03 }}
                >
                  <RepoCard repo={repo} onSelect={setSelectedRepo} />
                </motion.div>
              ))
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
