import { FormEvent, useMemo, useState } from 'react';
import { Bot, Loader2, Send, X } from 'lucide-react';
import * as api from '../api';
import { Candidate, JobRequirement, ReviewTask } from '../types';

interface AIAgentSidebarProps {
  isOpen: boolean;
  candidates: Candidate[];
  jobs: JobRequirement[];
  reviewTasks: ReviewTask[];
  onClose: () => void;
  onActionCompleted: () => Promise<void>;
}

type Message = api.AssistantMessage;

export default function AIAgentSidebar({
  isOpen,
  candidates,
  jobs,
  reviewTasks,
  onClose,
  onActionCompleted,
}: AIAgentSidebarProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content: 'I can help create job requirements, list active roles, and summarize pending review work using the current backend data.',
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  const prompts = useMemo(() => [
    'Create a Senior Python Engineer role in Remote with Python and FastAPI',
    'Show me active jobs',
    'What review cases need attention?',
  ], []);

  if (!isOpen) return null;

  const send = async (event?: FormEvent<HTMLFormElement>, override?: string) => {
    event?.preventDefault();
    const content = (override || input).trim();
    if (!content || loading) return;

    const nextMessages: Message[] = [...messages, { role: 'user', content }];
    setMessages(nextMessages);
    setInput('');
    setLoading(true);
    try {
      const result = await api.sendAssistantMessage(nextMessages, { candidates, jobs, reviewTasks });
      setMessages([...nextMessages, { role: 'assistant', content: result.text }]);
      if (result.actions.length > 0) {
        await onActionCompleted();
      }
    } catch (error) {
      setMessages([
        ...nextMessages,
        { role: 'assistant', content: error instanceof Error ? error.message : 'Assistant request failed.' },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/30">
      <button type="button" aria-label="Close workflow assistant" className="hidden flex-1 lg:block" onClick={onClose} />
      <aside className="flex h-full w-full max-w-md flex-col bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="rounded-md bg-cyan-50 p-2 text-cyan-700">
              <Bot className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-slate-950">Workflow Assistant</h2>
              <p className="text-sm text-slate-500">Uses configured LM Studio or external routing.</p>
            </div>
          </div>
          <button
            type="button"
            aria-label="Close assistant"
            onClick={onClose}
            className="rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          {messages.map((message, index) => (
            <div
              key={`${message.role}-${index}`}
              className={`rounded-md p-3 text-sm leading-6 ${
                message.role === 'user' ? 'ml-8 bg-slate-900 text-white' : 'mr-8 bg-slate-100 text-slate-700'
              }`}
            >
              {message.content}
            </div>
          ))}
          {loading && (
            <div className="mr-8 flex items-center gap-2 rounded-md bg-slate-100 p-3 text-sm text-slate-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              Working
            </div>
          )}
        </div>

        <div className="border-t border-slate-200 p-5">
          <div className="mb-3 flex flex-wrap gap-2">
            {prompts.map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={() => send(undefined, prompt)}
                disabled={loading}
                className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-200 disabled:opacity-50"
              >
                {prompt}
              </button>
            ))}
          </div>
          <form onSubmit={send} className="flex gap-2">
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Ask for a workflow action"
              className="h-10 min-w-0 flex-1 rounded-md border border-slate-200 px-3 text-sm outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100"
            />
            <button
              type="submit"
              aria-label="Send message"
              disabled={loading || !input.trim()}
              className="inline-flex h-10 w-10 items-center justify-center rounded-md bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-50"
            >
              <Send className="h-4 w-4" />
            </button>
          </form>
        </div>
      </aside>
    </div>
  );
}
