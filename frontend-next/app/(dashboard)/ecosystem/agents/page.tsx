"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"

export default function AgentsPage() {
  const router = useRouter()
  useEffect(() => { router.replace("/ecosystem") }, [router])
  return null
}
