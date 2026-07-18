import { z } from "zod"

export const loginSchema = z.object({
  email: z.string().email("Invalid email address"),
  password: z.string().min(8, "Password must be at least 8 characters"),
})

export const registerSchema = z.object({
  name: z.string().min(2, "Name must be at least 2 characters"),
  email: z.string().email("Invalid email address"),
  password: z.string().min(8, "Password must be at least 8 characters"),
  confirmPassword: z.string(),
}).refine((data) => data.password === data.confirmPassword, {
  message: "Passwords don't match",
  path: ["confirmPassword"],
})

export const generateSchema = z.object({
  prompt: z.string().min(10, "Prompt must be at least 10 characters").max(500, "Prompt too long"),
  projectName: z.string().max(100).optional(),
  model: z.string().optional(),
})

export const stackConfigSchema = z.object({
  backend: z.enum(["fastapi", "flask", "express", "spring", "go-gin", "none"]).default("fastapi"),
  frontend: z.enum(["streamlit", "react", "vue", "angular", "svelte", "html", "none"]).default("react"),
  db: z.enum(["sqlite", "postgresql", "mysql", "mongodb", "redis", "dynamodb", "none"]).default("sqlite"),
  css: z.enum(["none", "bootstrap", "tailwind", "bulma", "materialize"]).default("tailwind"),
  testing: z.enum(["pytest", "unittest", "jest", "mocha", "vitest", "none"]).default("pytest"),
  orm: z.enum(["none", "sqlalchemy", "prisma", "typeorm", "django-orm", "mongoose", "sqlx"]).default("sqlalchemy"),
  auth: z.enum(["none", "jwt", "oauth2", "session", "firebase", "auth0"]).default("jwt"),
  deploy: z.enum(["none", "docker", "docker-compose", "kubernetes", "serverless", "heroku"]).default("docker"),
})

export type LoginFormData = z.infer<typeof loginSchema>
export type RegisterFormData = z.infer<typeof registerSchema>
export type GenerateFormData = z.infer<typeof generateSchema>
export type StackConfig = z.infer<typeof stackConfigSchema>
