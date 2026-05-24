import { useState, useRef, useEffect } from 'react';
import { Sparkles, Send, X, Bot, User, Trash2, Cpu, RefreshCw, Terminal, CheckCircle, Briefcase } from 'lucide-react';
import { Candidate, JobRequirement, ReviewTask } from '../types';

const LS_KEY = 'bld_ai_chats';

interface AIAgentSidebarProps {
  isOpen: boolean;
  onClose: () => void;
  candidates: Candidate[];
  jobs: JobRequirement[];
  reviewTasks: ReviewTask[];
  onJobCreated?: () => void;
  onNavigate?: (screen: 'candidates' | 'jobs' | 'review' | 'audit' | 'settings') => void;
}

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  actionCard?: { type: string; title: string; subtitle: string };
}

const DEFAULT_MESSAGES: Message[] = [
  {
    role: 'assistant',
    content: `Hello! I am the **Bloodhound AI Copilot**.

I have real-time access to the talent pool and job matrix. You can ask me to:
- **Create jobs**: "Create a job for a Senior Python Developer in Berlin."
- **Search jobs**: "Find all remote engineering roles."
- **Audit compliance**: "What GDPR tasks are pending?"
- **Pool overview**: "How many candidates do we have?"`,
    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }
];

function loadMessages(): Message[] {
  try {
    const stored = localStorage.getItem(LS_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }
  } catch {
    // corrupted storage — fall back to defaults
  }
  return DEFAULT_MESSAGES;
}

function saveMessages(msgs: Message[]) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(msgs));
  } catch {
    // storage quota exceeded — ignore
  }
}

export default function AIAgentSidebar({
  isOpen,
  onClose,
  candidates,
  jobs,
  reviewTasks,
  onJobCreated,
  onNavigate,
}: AIAgentSidebarProps) {
  const [messages, setMessages] = useState<Message[]>(loadMessages);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Persist messages to localStorage whenever they change
  useEffect(() => {
    saveMessages(messages);
  }, [messages]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isOpen]);

  const handleSendMessage = async (textToSend: string) => {
    if (!textToSend.trim() || isLoading) return;

    const userMsg: Message = {
      role: 'user',
      content: textToSend.trim(),
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);

    try {
      const chatHistoryForAPI = [...messages, userMsg].map((m) => ({
        role: m.role,
        content: m.content
      }));

      const res = await fetch("/api/gemini/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: chatHistoryForAPI,
          context: {
            candidates,
            jobs,
            reviewTasks
          }
        })
      });

      if (!res.ok) {
        throw new Error(`Server returned error code: ${res.status}`);
      }

      const data = await res.json();

      const actions: Array<{ type: string; data?: Record<string, unknown> }> = data.actions || [];

      // Handle side-effects from agent actions
      const jobCreated = actions.find((a) => a.type === 'job_created');
      if (jobCreated) {
        onJobCreated?.();
      }

      const actionCard = jobCreated && jobCreated.data
        ? {
            type: 'job_created',
            title: String((jobCreated.data as Record<string, unknown>).title || 'New Job'),
            subtitle: `${(jobCreated.data as Record<string, unknown>).location || ''} • ${(jobCreated.data as Record<string, unknown>).department || ''}`.trim().replace(/^•\s*/, ''),
          }
        : undefined;

      const assistantMsg: Message = {
        role: 'assistant',
        content: data.text || "I was unable to retrieve a response from the database ledger.",
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        actionCard,
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: any) {
      console.error(err);
      const errorMsg: Message = {
        role: 'assistant',
        content: `❌ **Service Connection Alert**
        
Unable to connect to the backend agent server. Verify your \`API_KEY\` is configured in the settings secrets pane.

*Technical: ${err.message || String(err)}*`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  const clearChat = () => {
    const reset: Message[] = [
      {
        role: 'assistant',
        content: "Context cleared. How can I assist? Try: _\"Create a job for a Senior Python Developer\"_ or _\"Show me all active roles\"_.",
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      }
    ];
    setMessages(reset);
    saveMessages(reset);
  };

  const samplePrompts = [
    "Create a job for a Senior React Developer in Berlin",
    "Find all remote engineering roles",
    "How many candidates are in the pool?",
    "What GDPR compliance tasks are pending?"
  ];

  const formatMarkdown = (text: string) => {
    const lines = text.split("\n");
    return lines.map((line, idx) => {
      let content = line;
      let className = "text-xs leading-relaxed break-words font-sans";

      if (content.trim() === "") {
        return <div key={idx} className="h-2" />;
      }
      if (content.startsWith("### ")) {
        return <h4 key={idx} className="text-xs font-mono font-bold text-bloodhound-crimson mt-3 mb-1 uppercase tracking-wider">{content.substring(4)}</h4>;
      }
      if (content.startsWith("## ") || content.startsWith("# ")) {
        return <h3 key={idx} className="text-sm font-bold text-slate-deep mt-4 mb-1 border-b border-gray-100 pb-0.5">{content.replace(/^#+\s+/, "")}</h3>;
      }
      if (content.startsWith("❌") || content.startsWith("⚠️") || content.startsWith("✔")) {
        className += " py-1.5 px-2 bg-red-50/70 border-l-2 border-red-400 rounded-r text-[11px] text-red-900";
      }
      if (content.trim().startsWith("- ") || content.trim().startsWith("* ")) {
        const raw = content.trim().substring(2);
        return (
          <li key={idx} className="list-disc list-inside text-xs leading-relaxed text-on-surface-variant font-sans ml-2.5 my-0.5">
            {parseInlineStyles(raw)}
          </li>
        );
      }
      return (
        <p key={idx} className={className}>
          {parseInlineStyles(content)}
        </p>
      );
    });
  };

  const parseInlineStyles = (rawText: string) => {
    const regex = /(\*\*.*?\*\*|`.*?`)/g;
    const splitParts = rawText.split(regex);
    if (splitParts.length === 1) return rawText;
    return splitParts.map((part, i) => {
      if (part.startsWith("**") && part.endsWith("**")) {
        return <strong key={i} className="font-bold text-slate-deep">{part.slice(2, -2)}</strong>;
      }
      if (part.startsWith("`") && part.endsWith("`")) {
        return <code key={i} className="font-mono text-[10px] bg-slate-100 border border-slate-200/60 px-1 py-0.5 rounded text-bloodhound-crimson">{part.slice(1, -1)}</code>;
      }
      return part;
    });
  };

  if (!isOpen) return null;

  return (
    <div 
      id="ai-copilot-aside"
      className="fixed inset-y-0 right-0 z-50 w-96 border-l border-border-subtle bg-white shadow-2xl flex flex-col h-screen animate-in slide-in-from-right duration-200"
    >
      {/* Sidebar Header */}
      <div className="p-4 bg-slate-deep text-white border-b border-slate-700/50 flex justify-between items-center shrink-0">
        <div className="flex items-center gap-2">
          <div className="p-1 px-2 rounded bg-amber-500/10 border border-amber-500/20 text-amber-400 animate-pulse">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <h3 className="font-sans font-bold text-sm leading-tight text-white flex items-center gap-1.5">
              <span>Bloodhound</span>
            </h3>
            <p className="text-[10px] text-white/65 font-mono">BLODDHOUND AI</p>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <button
            id="flushed-chat-logs-btn"
            onClick={clearChat}
            className="p-1.5 hover:bg-slate-700 text-white/80 hover:text-white rounded transition-colors cursor-pointer"
            title="Clear context logs"
          >
            <Trash2 className="w-4 h-4" />
          </button>
          <button
            id="close-ai-copilot-btn"
            onClick={onClose}
            className="p-1.5 hover:bg-slate-700 text-white/80 hover:text-white rounded transition-colors cursor-pointer"
            title="Collapse panel"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Database Context Stats Bar */}
      <div className="px-4 py-2 bg-slate-100 border-b border-border-subtle flex items-center justify-between text-[10px] font-mono font-semibold text-slate-500 shrink-0">
        <div className="flex items-center gap-1">
          <Cpu className="w-3.5 h-3.5 text-slate-deep" />
          <span>LEDGER DECODER ACTIVE</span>
        </div>
        <div className="flex items-center gap-2.5">
          <span>ND={candidates.length}</span>
          <span>● QB={reviewTasks.length}</span>
        </div>
      </div>

      {/* Scrollable conversation logs context */}
      <div 
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-4 space-y-4 no-scrollbar bg-slate-50/50"
      >
        {messages.map((msg, index) => {
          const isAI = msg.role === 'assistant';
          return (
            <div 
              key={index}
              className={`flex gap-2.5 max-w-[88%] ${isAI ? 'mr-auto' : 'ml-auto flex-row-reverse'}`}
            >
              <div className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 border text-[11px] font-bold ${
                isAI ? 'bg-amber-50 border-amber-200 text-amber-600' : 'bg-slate-deep border-slate-600 text-white'
              }`}>
                {isAI ? <Bot className="w-3.5 h-3.5" /> : <User className="w-3.5 h-3.5" />}
              </div>

              <div className="space-y-1">
                <div className={`p-3 rounded-lg border text-xs shadow-xs transition-shadow ${
                  isAI
                    ? 'bg-white border-border-subtle text-slate-800 rounded-tl-none'
                    : 'bg-slate-deep border-slate-700 text-white rounded-tr-none'
                }`}>
                  <div className="space-y-1.5">
                    {formatMarkdown(msg.content)}
                  </div>
                </div>

                {msg.actionCard?.type === 'job_created' && (
                  <div
                    className="mt-1.5 p-2.5 bg-emerald-50 border border-emerald-200 rounded-lg flex items-center gap-2.5 cursor-pointer hover:bg-emerald-100 transition-colors"
                    onClick={() => onNavigate?.('jobs')}
                    title="Go to Job Match Matrix"
                  >
                    <div className="p-1 bg-emerald-100 rounded border border-emerald-200 shrink-0">
                      <Briefcase className="w-3.5 h-3.5 text-emerald-700" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-[11px] font-bold text-emerald-800 truncate">{msg.actionCard.title}</p>
                      {msg.actionCard.subtitle && (
                        <p className="text-[10px] text-emerald-600 font-mono truncate">{msg.actionCard.subtitle}</p>
                      )}
                    </div>
                    <CheckCircle className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                  </div>
                )}

                <span className={`block text-[9px] font-mono text-slate-400 ${isAI ? 'text-left' : 'text-right'}`}>
                  {msg.timestamp}
                </span>
              </div>
            </div>
          );
        })}

        {isLoading && (
          <div className="flex gap-2.5 mr-auto max-w-[80%] items-center">
            <div className="w-6 h-6 rounded-full flex items-center justify-center bg-amber-50 border border-amber-200 text-amber-600 animate-spin">
              <RefreshCw className="w-3.5 h-3.5" />
            </div>
            <div className="px-3 py-2 bg-white border border-border-subtle rounded-lg text-xs text-slate-500 font-mono animate-pulse">
              Running deep ledger sweep query...
            </div>
          </div>
        )}
      </div>

      {messages.length < 3 && !isLoading && (
        <div className="px-4 py-2 bg-slate-50 border-t border-border-subtle shrink-0">
          <p className="text-[10px] font-bold font-mono text-slate-500 uppercase tracking-wider mb-1.5 flex items-center gap-1">
            <Terminal className="w-3 h-3 text-slate-400" />
            <span>AI ACTIONS CONSOLE:</span>
          </p>
          <div className="flex flex-wrap gap-1.5">
            {samplePrompts.map((prompt, idx) => (
              <button
                key={idx}
                onClick={() => handleSendMessage(prompt)}
                className="text-[10px] text-slate-deep hover:bg-slate-200 border border-slate-300 bg-white font-sans font-medium px-2 py-1 rounded cursor-pointer transition-colors max-w-full truncate"
                title={prompt}
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="p-4 bg-white border-t border-border-subtle shrink-0">
        <form 
          onSubmit={(e) => {
            e.preventDefault();
            handleSendMessage(input);
          }}
          className="flex gap-2"
        >
          <input
            id="ai-chat-input-box"
            type="text"
            placeholder="Type your audit query here..."
            className="flex-1 bg-slate-50 hover:bg-slate-100 border border-border-subtle hover:border-slate-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-slate-deep rounded px-3 py-2 text-xs text-slate-800"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={isLoading}
          />
          <button
            id="ai-chat-send-btn"
            type="submit"
            disabled={!input.trim() || isLoading}
            className="px-3 bg-slate-deep text-white rounded hover:bg-black transition-colors flex items-center justify-center disabled:opacity-40 cursor-pointer"
          >
            <Send className="w-3.5 h-3.5" />
          </button>
        </form>

        <p className="text-[9px] text-center text-slate-400 font-mono mt-2 uppercase tracking-wide">
          Bloodhound Vault Ledger Sandbox Protected
        </p>
      </div>
    </div>
  );
}
