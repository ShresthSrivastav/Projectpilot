"use client"

import ReactMarkdown from "react-markdown"
import dynamic from "next/dynamic"
import rehypeSanitize from "rehype-sanitize"
import { Copy, Check } from "lucide-react"
import { useState, useCallback } from "react"
import { cn } from "@/lib/utils/cn"
import type { Components } from "react-markdown"
import type { CSSProperties } from "react"

const SyntaxHighlighter = dynamic(() => import("react-syntax-highlighter").then(m => m.Prism), { ssr: false })
const oneDark: Record<string, CSSProperties> = {
  'code[class*="language-"]': { color: "#abb2bf", background: "none", fontFamily: "JetBrains Mono, monospace", fontSize: "12px", textAlign: "left", whiteSpace: "pre", wordSpacing: "normal", wordBreak: "normal", wordWrap: "normal", lineHeight: "1.6", tabSize: 4, hyphens: "none" },
  'pre[class*="language-"]': { color: "#abb2bf", background: "hsl(0, 0%, 7%)", fontFamily: "JetBrains Mono, monospace", fontSize: "12px", textAlign: "left", whiteSpace: "pre", wordSpacing: "normal", wordBreak: "normal", wordWrap: "normal", lineHeight: "1.6", tabSize: 4, hyphens: "none", overflow: "auto" },
  comment: { color: "#5c6370", fontStyle: "italic" },
  prolog: { color: "#5c6370" },
  cdata: { color: "#5c6370" },
  punctuation: { color: "#abb2bf" },
  "selector, tag": { color: "#e06c75" },
  "property-value, operator": { color: "#d19a66" },
  "tag-id": { color: "#d19a66" },
  "attr-name": { color: "#e06c75" },
  "boolean, number": { color: "#d19a66" },
  "class-name, function": { color: "#61afef" },
  "string, char": { color: "#98c379" },
  "property, keyword": { color: "#c678dd" },
  "regex, important": { color: "#98c379" },
  "atrule, url": { color: "#56b6c2" },
}

interface CopyButtonProps {
  code: string
}

function CopyButton({ code }: CopyButtonProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }, [code])

  return (
    <button
      onClick={handleCopy}
      aria-label="Copy code"
      className="absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-md bg-muted/50 text-muted-foreground opacity-0 transition-opacity hover:bg-muted hover:text-foreground group-hover/code:opacity-100"
    >
      {copied ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  )
}

const components: Components = {
  code({ className, children, ...props }) {
    const match = /language-(\w+)/.exec(className ?? "")
    const codeString = String(children).replace(/\n$/, "")

    if (match) {
      return (
        <div className="group/code relative my-3 overflow-hidden rounded-lg border border-border">
          <div className="flex items-center justify-between border-b border-border bg-muted/50 px-3 py-1.5">
            <span className="text-[10px] font-mono text-muted-foreground/70">{match[1]}</span>
          </div>
          <SyntaxHighlighter
            style={oneDark}
            language={match[1]}
            PreTag="div"
            customStyle={{
              margin: 0,
              borderRadius: 0,
              fontSize: "12px",
              lineHeight: "1.6",
              background: "hsl(0, 0%, 7%)",
            }}
            showLineNumbers
          >
            {codeString}
          </SyntaxHighlighter>
          <CopyButton code={codeString} />
        </div>
      )
    }

    return (
      <code
        className="rounded bg-muted px-1.5 py-0.5 text-xs font-mono text-primary"
        {...props}
      >
        {children}
      </code>
    )
  },
  pre({ children }) {
    return <>{children}</>
  },
  p({ children }) {
    return <p className="text-sm leading-relaxed mb-3 last:mb-0">{children}</p>
  },
  ul({ children }) {
    return <ul className="list-disc pl-5 space-y-1 mb-3 text-sm">{children}</ul>
  },
  ol({ children }) {
    return <ol className="list-decimal pl-5 space-y-1 mb-3 text-sm">{children}</ol>
  },
  li({ children }) {
    return <li className="text-sm leading-relaxed">{children}</li>
  },
  h1({ children }) {
    return <h1 className="text-lg font-semibold mt-4 mb-2">{children}</h1>
  },
  h2({ children }) {
    return <h2 className="text-base font-semibold mt-3 mb-2">{children}</h2>
  },
  h3({ children }) {
    return <h3 className="text-sm font-semibold mt-3 mb-1">{children}</h3>
  },
  blockquote({ children }) {
    return (
      <blockquote className="border-l-2 border-primary/30 pl-4 py-1 my-3 text-sm text-muted-foreground italic">
        {children}
      </blockquote>
    )
  },
  a({ href, children }) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-primary underline underline-offset-2 hover:text-accent transition-colors"
      >
        {children}
      </a>
    )
  },
  hr() {
    return <hr className="my-4 border-border" />
  },
  table({ children }) {
    return (
      <div className="my-3 overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">{children}</table>
      </div>
    )
  },
  thead({ children }) {
    return <thead className="bg-muted/50">{children}</thead>
  },
  th({ children }) {
    return <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">{children}</th>
  },
  td({ children }) {
    return <td className="px-3 py-2 text-sm border-t border-border">{children}</td>
  },
}

interface MarkdownRendererProps {
  content: string
  className?: string
}

export function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  return (
    <div className={cn("prose prose-sm dark:prose-invert max-w-none", className)}>
      <ReactMarkdown components={components} rehypePlugins={[rehypeSanitize]}>{content}</ReactMarkdown>
    </div>
  )
}
