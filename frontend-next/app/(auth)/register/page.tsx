"use client"

import { useState } from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import Link from "next/link"
import { registerSchema, type RegisterFormData } from "@/lib/utils/validators"
import { useAuth } from "@/lib/hooks/use-auth"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { PanelRightOpen, Loader2 } from "lucide-react"

export default function RegisterPage() {
  const { register: registerUser } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const { register, handleSubmit, formState: { errors }, watch } = useForm<RegisterFormData>({
    resolver: zodResolver(registerSchema),
  })

  const password = watch("password", "") // eslint-disable-line react-hooks/incompatible-library

  const onSubmit = async (data: RegisterFormData) => {
    setLoading(true)
    setError(null)
    try {
      await registerUser(data.name, data.email, data.password)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Registration failed"
      setError(message === "Email already registered" ? "Email already registered. Sign in instead." : message)
    } finally {
      setLoading(false)
    }
  }

  const strengthColor =
    password.length < 6 ? "bg-error" : password.length < 10 ? "bg-warning" : "bg-success"
  const strengthWidth =
    password.length < 6 ? "25%" : password.length < 10 ? "50%" : "100%"

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center bg-background">
      <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-accent/5" />
      <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:64px_64px]" />

      <div className="relative z-10 w-full max-w-sm space-y-6 px-4">
        <div className="flex flex-col items-center space-y-2 text-center">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary shadow-glow">
            <PanelRightOpen className="h-5 w-5 text-primary-foreground" />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">Create an account</h1>
          <p className="text-sm text-muted-foreground">Start building with ProjectPilot</p>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Name</Label>
            <Input id="name" placeholder="Your name" {...register("name")} />
            {errors.name && <p className="text-xs text-error">{errors.name.message}</p>}
          </div>

          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" placeholder="name@example.com" {...register("email")} />
            {errors.email && <p className="text-xs text-error">{errors.email.message}</p>}
          </div>

          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <Input id="password" type="password" placeholder="••••••••" {...register("password")} />
            {password && (
              <div className="h-1 w-full rounded-full bg-muted overflow-hidden">
                <div className={`h-full rounded-full transition-all ${strengthColor}`} style={{ width: strengthWidth }} />
              </div>
            )}
            {errors.password && <p className="text-xs text-error">{errors.password.message}</p>}
          </div>

          <div className="space-y-2">
            <Label htmlFor="confirmPassword">Confirm Password</Label>
            <Input
              id="confirmPassword"
              type="password"
              placeholder="••••••••"
              {...register("confirmPassword")}
            />
            {errors.confirmPassword && (
              <p className="text-xs text-error">{errors.confirmPassword.message}</p>
            )}
          </div>

          {error && (
            <div className="rounded-md bg-error/10 border border-error/20 p-3">
              <p className="text-xs text-error">{error}</p>
            </div>
          )}

          <Button type="submit" className="w-full" disabled={loading}>
            {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Create Account
          </Button>
        </form>

        <p className="text-center text-sm text-muted-foreground">
          Already have an account?{" "}
          <Link href="/login" className="text-primary hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  )
}
