export function StatusPill({ state, children }: { state: "loading" | "success" | "error"; children: React.ReactNode }) {
  return <span className={`connection ${state}`}>{children}</span>;
}
