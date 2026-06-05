import { Screen } from './Sidebar';

interface RouteSkeletonProps {
  screen: Screen;
}

function Block({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-slate-200/70 ${className}`} />;
}

function CardGrid() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {Array.from({ length: 4 }).map((_, index) => (
        <div key={index} className="rounded-md border border-slate-200 bg-white p-5">
          <Block className="h-3 w-24" />
          <Block className="mt-4 h-8 w-16" />
        </div>
      ))}
    </div>
  );
}

function TableSkeleton() {
  return (
    <div className="overflow-hidden rounded-md border border-slate-200 bg-white">
      <div className="border-b border-slate-200 bg-slate-50 px-4 py-3">
        <Block className="h-3 w-40" />
      </div>
      <div className="divide-y divide-slate-100">
        {Array.from({ length: 6 }).map((_, index) => (
          <div key={index} className="flex items-center gap-4 px-4 py-4">
            <Block className="h-10 w-10 shrink-0 rounded-md" />
            <Block className="h-4 w-48" />
            <Block className="ml-auto h-4 w-24" />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function RouteSkeleton({ screen }: RouteSkeletonProps) {
  const showCards = screen === 'overview' || screen === 'maintenance';

  return (
    <div className="space-y-5" aria-busy="true" aria-label="Loading content">
      {showCards && <CardGrid />}
      <TableSkeleton />
    </div>
  );
}
