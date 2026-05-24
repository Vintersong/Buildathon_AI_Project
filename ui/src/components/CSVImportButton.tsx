import { useRef, useState } from 'react';
import { FileSpreadsheet, Loader2, CheckCircle2, XCircle } from 'lucide-react';
import { startCSVIngest, pollCSVIngest, CSVIngestProgress } from '../api';

interface Props {
  onDone: () => Promise<void>;
  onToast: (message: string, type?: 'success' | 'info' | 'error') => void;
}

export default function CSVImportButton({ onDone, onToast }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [progress, setProgress] = useState<CSVIngestProgress | null>(null);
  const [uploading, setUploading] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const handleFile = async (file: File) => {
    if (!/\.(csv|xlsx|xlsm)$/i.test(file.name)) {
      onToast('Only .csv, .xlsx, and .xlsm files are supported.', 'error');
      return;
    }
    setUploading(true);
    setProgress(null);
    try {
      const { task_id } = await startCSVIngest(file);
      pollRef.current = setInterval(async () => {
        try {
          const p = await pollCSVIngest(task_id);
          setProgress(p);
          if (p.done) {
            stopPolling();
            setUploading(false);
            onToast(
              `Spreadsheet import done: ${p.processed} candidate(s), ${p.jobs_created} job(s), ${p.skipped} skipped, ${p.failed} failed.`,
              p.failed > 0 ? 'info' : 'success',
            );
            await onDone();
          }
        } catch {
          stopPolling();
          setUploading(false);
          onToast('Lost contact with ingest task.', 'error');
        }
      }, 1500);
    } catch (e) {
      setUploading(false);
      onToast(e instanceof Error ? e.message : 'Spreadsheet upload failed', 'error');
    }
  };

  const pct = progress && progress.total > 0 ? Math.round((progress.rows_seen / progress.total) * 100) : null;

  return (
    <div className="flex flex-col gap-2">
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.xlsx,.xlsm"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
          e.target.value = '';
        }}
      />
      <button
        type="button"
        disabled={uploading}
        onClick={() => inputRef.current?.click()}
        className="inline-flex h-10 items-center gap-2 rounded-md border border-slate-200 px-3 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
      >
        {uploading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <FileSpreadsheet className="h-4 w-4 text-emerald-600" />
        )}
        Import CSV/Excel
      </button>

      {progress && (
        <div className="rounded-md border border-slate-200 bg-white p-3 text-xs">
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <span className="font-medium text-slate-700">
              {progress.done ? (
                progress.failed > 0 ? (
                  <span className="flex items-center gap-1 text-amber-700">
                    <XCircle className="h-3.5 w-3.5" /> Done with errors
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-emerald-700">
                    <CheckCircle2 className="h-3.5 w-3.5" /> Import complete
                  </span>
                )
              ) : (
                'Importing...'
              )}
            </span>
            {pct !== null && <span className="text-slate-500">{pct}%</span>}
          </div>

          <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full rounded-full bg-cyan-500 transition-all duration-300"
              style={{ width: `${pct ?? 0}%` }}
            />
          </div>

          <div className="mt-2 flex flex-wrap gap-4 text-slate-500">
            <span>{progress.processed} candidates</span>
            <span>{progress.jobs_created} jobs</span>
            <span>{progress.skipped} skipped</span>
            {progress.failed > 0 && <span className="text-rose-600">{progress.failed} failed</span>}
          </div>

          {progress.errors.length > 0 && (
            <ul className="mt-2 space-y-0.5 text-rose-600">
              {progress.errors.slice(0, 5).map((e, i) => (
                <li key={i}>Row {e.row}: {e.error}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
