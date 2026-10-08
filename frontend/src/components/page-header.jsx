export default function PageHeader({ title, description, actions, children }) {
  return (
    <header className="flex flex-col gap-4 border-b border-border bg-background px-5 py-4 sm:px-8 sm:py-5 lg:flex-row lg:items-center lg:justify-between">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight text-balance sm:text-2xl">
          {title}
        </h1>
        {description && (
          <p className="mt-1 max-w-[65ch] text-sm text-pretty text-muted-foreground">
            {description}
          </p>
        )}
      </div>
      {(actions || children) && (
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {actions}
          {children}
        </div>
      )}
    </header>
  );
}
