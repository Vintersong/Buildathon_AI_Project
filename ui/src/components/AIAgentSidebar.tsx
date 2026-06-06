import { FormEvent, useMemo, useState } from 'react';
import { Ban, Bot, CheckCircle2, Loader2, Send, ShieldCheck, X } from 'lucide-react';
import * as api from '../api';
import { Candidate, JobRequirement, ReviewTask } from '../types';
import { Screen } from './Sidebar';

interface AIAgentSidebarProps {
  isOpen: boolean;
  activeScreen: Screen;
  candidates: Candidate[];
  jobs: JobRequirement[];
  reviewTasks: ReviewTask[];
  onClose: () => void;
  onActionCompleted: () => Promise<void>;
}

const DEFAULT_ACTIONS = [
  'Create a Senior Python Engineer role in Remote with Python and FastAPI',
  'Run shortlist for the newest active job',
  'Find stale profiles older than 6 months',
  'Show me active jobs',
  'What review cases need attention?',
];

// Quick actions are deterministic, task-oriented prompts scoped to the active
// center-canvas surface — the assistant acts as a contextual executor rather
// than an open-ended chat box.
const QUICK_ACTIONS: Record<Screen, string[]> = {
  overview: DEFAULT_ACTIONS,
  talent: [
    'Group these candidates into a shortlist',
    'Find likely duplicate profiles',
    'Flag profiles older than 6 months',
  ],
  jobs: [
    'Run shortlist for the newest active job',
    'Draft outreach for the top match',
    'Show me active jobs',
  ],
  projects: [
    'Match candidates to the newest project',
    'Summarize open project prospects',
    'Which candidates fit this project?',
  ],
  review: [
    'Explain why these cases were flagged',
    'Summarize pending compliance flags',
    'What review cases need attention?',
  ],
  maintenance: [
    'Find stale profiles older than 6 months',
    'Process the intake folder',
    'Summarize audit health',
  ],
  settings: DEFAULT_ACTIONS,
};

const SCREEN_LABELS: Record<Screen, string> = {
  overview: 'Overview',
  talent: 'Talent Pool',
  jobs: 'Jobs & Shortlist',
  projects: 'Projects',
  review: 'Outreach & Review',
  maintenance: 'Maintenance',
  settings: 'Settings',
};

type Message = api.AssistantMessage & {
  proposals?: api.AgentProposal[];
  actions?: api.AgentAction[];
  errors?: string[];
};

type ProposalStatus = 'idle' | 'loading' | 'confirmed' | 'cancelled' | 'error';

export default function AIAgentSidebar({
  isOpen,
  activeScreen,
  candidates,
  jobs,
  reviewTasks,
  onClose,
  onActionCompleted,
}: AIAgentSidebarProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content: 'I can prepare local talent-pool workflow actions for human confirmation: jobs, shortlists, outreach drafts, review work, intake, and stale-profile maintenance.',
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [proposalStates, setProposalStates] = useState<Record<string, { status: ProposalStatus; error?: string }>>({});

  const prompts = useMemo(() => QUICK_ACTIONS[activeScreen] ?? DEFAULT_ACTIONS, [activeScreen]);

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
      const assistantMessages = nextMessages.map(({ role, content }) => ({ role, content }));
      const result = await api.sendAssistantMessage(assistantMessages, { candidates, jobs, reviewTasks });
      setMessages([
        ...nextMessages,
        {
          role: 'assistant',
          content: result.text,
          proposals: result.proposals || [],
          actions: result.actions || [],
          errors: result.errors || [],
        },
      ]);
      if ((result.actions || []).length > 0) {
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

  const confirmProposal = async (proposal: api.AgentProposal) => {
    const current = proposalStates[proposal.id]?.status;
    if (current === 'loading' || current === 'confirmed' || current === 'cancelled') return;

    setProposalStates((prev) => ({ ...prev, [proposal.id]: { status: 'loading' } }));
    try {
      const result = await api.confirmAssistantProposal(proposal.id);
      setProposalStates((prev) => ({ ...prev, [proposal.id]: { status: 'confirmed' } }));
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: result.text,
          actions: result.actions || [],
          errors: result.errors || [],
        },
      ]);
      if ((result.actions || []).length > 0) {
        await onActionCompleted();
      }
    } catch (error) {
      setProposalStates((prev) => ({
        ...prev,
        [proposal.id]: {
          status: 'error',
          error: error instanceof Error ? error.message : 'Confirmation failed.',
        },
      }));
    }
  };

  const cancelProposal = (proposalId: string) => {
    setProposalStates((prev) => ({ ...prev, [proposalId]: { status: 'cancelled' } }));
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
              <p className="text-sm text-slate-500">Local workflow proposals with human confirmation.</p>
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
            <div key={`${message.role}-${index}`} className="space-y-3">
              <div
                className={`whitespace-pre-wrap rounded-md p-3 text-sm leading-6 ${
                  message.role === 'user' ? 'ml-8 bg-slate-900 text-white' : 'mr-8 bg-slate-100 text-slate-700'
                }`}
              >
                {message.content}
              </div>
              {message.proposals?.map((proposal) => {
                const state = proposalStates[proposal.id] || { status: 'idle' as ProposalStatus };
                return (
                  <div key={proposal.id} className="mr-8 rounded-md border border-cyan-200 bg-white p-4 shadow-sm">
                    <div className="flex items-start gap-3">
                      <div className="rounded-md bg-cyan-50 p-2 text-cyan-700">
                        <ShieldCheck className="h-4 w-4" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-semibold text-slate-950">{proposal.label}</p>
                        <p className="mt-1 text-sm leading-5 text-slate-600">{proposal.description}</p>
                        <p className="mt-2 text-xs leading-5 text-slate-500">{proposal.impact}</p>
                        {state.error && (
                          <p className="mt-2 rounded-md bg-rose-50 px-2 py-1 text-xs text-rose-700">{state.error}</p>
                        )}
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button
                            type="button"
                            onClick={() => confirmProposal(proposal)}
                            disabled={state.status !== 'idle' && state.status !== 'error'}
                            className="inline-flex items-center gap-2 rounded-md bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            {state.status === 'loading' ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <CheckCircle2 className="h-3.5 w-3.5" />
                            )}
                            {state.status === 'confirmed' ? 'Confirmed' : 'Confirm'}
                          </button>
                          <button
                            type="button"
                            onClick={() => cancelProposal(proposal.id)}
                            disabled={state.status !== 'idle' && state.status !== 'error'}
                            className="inline-flex items-center gap-2 rounded-md border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            <Ban className="h-3.5 w-3.5" />
                            {state.status === 'cancelled' ? 'Cancelled' : 'Cancel'}
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
              {message.errors?.map((error) => (
                <div key={error} className="mr-8 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
                  {error}
                </div>
              ))}
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
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">
            Quick actions · {SCREEN_LABELS[activeScreen]}
          </p>
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
