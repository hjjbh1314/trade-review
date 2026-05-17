import { useEffect, useRef, useState } from 'react';
import type { ChatFocus, ChatMessage } from '../api';
import { streamChatMessage } from '../api';

const QUICK_PROMPTS = [
  '现在该止损还是持有？',
  '这只股票明天怎么看？',
  '给我一个 T+0 策略',
  '对比一下同行业股票',
];

export function ChatPanel({ focus }: { focus: ChatFocus | null }) {
  const focusKey = focus?.symbol && focus?.market ? `${focus.market}:${focus.symbol}` : 'none';
  return <ChatConversation key={focusKey} focus={focus} />;
}

function ChatConversation({ focus }: { focus: ChatFocus | null }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [loading, setLoading] = useState(false);
  const [phase, setPhase] = useState('');
  const [streamBuffer, setStreamBuffer] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // 自动滚到底
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, streamBuffer]);

  async function send(text: string) {
    if (!text.trim() || loading) return;
    const newMsgs: ChatMessage[] = [...messages, { role: 'user', content: text }];
    setMessages(newMsgs);
    setDraft('');
    setStreamBuffer('');
    setErr(null);
    setLoading(true);
    setPhase('');

    try {
      let buf = '';
      for await (const ev of streamChatMessage(newMsgs, focus)) {
        switch (ev.type) {
          case 'status': setPhase(ev.data.phase); break;
          case 'chunk':
            buf += ev.data.text;
            setStreamBuffer(buf);
            break;
          case 'done':
            setMessages(m => [...m, { role: 'assistant', content: buf }]);
            setStreamBuffer('');
            break;
          case 'error':
            setErr(ev.data.message);
            break;
        }
      }
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
      setPhase('');
    }
  }

  function newConversation() {
    setMessages([]);
    setStreamBuffer('');
    setErr(null);
  }

  return (
    <div className="sticky top-20 bg-white border border-cream-300 rounded-xl flex flex-col"
         style={{ height: 'calc(100vh - 120px)' }}>
      <div className="flex items-center justify-between px-4 py-3 border-b border-cream-300">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-full bg-clay-500 flex items-center justify-center text-xs font-bold text-white">AI</div>
          <div>
            <div className="text-sm font-semibold text-ink-900">复盘助手</div>
            <div className="text-xs text-ink-400">
              {focus?.symbol ? `聚焦：${focus.name ?? focus.symbol}` : '未聚焦持仓'}
            </div>
          </div>
        </div>
        <button onClick={newConversation}
                className="text-xs text-ink-500 hover:text-ink-900 border border-cream-300 px-2 py-1 rounded">
          新对话
        </button>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-thin px-4 py-4 space-y-4 text-sm">
        {messages.length === 0 && !streamBuffer && (
          <div className="text-xs text-ink-400 text-center py-8">
            {focus?.symbol
              ? `针对 ${focus.name ?? focus.symbol} 问点什么吧`
              : '左侧选一只持仓后开始问'}
          </div>
        )}

        {messages.map((m, i) => (
          <MessageBubble key={i} role={m.role} content={m.content} />
        ))}

        {loading && streamBuffer && (
          <MessageBubble role="assistant" content={streamBuffer} streaming />
        )}

        {loading && !streamBuffer && phase && (
          <div className="flex gap-2">
            <div className="w-6 h-6 rounded-full bg-clay-500 shrink-0 mt-0.5 animate-pulse"></div>
            <div className="bg-cream-100 border border-cream-300 rounded-lg px-3 py-2 text-xs text-ink-500">
              {phase === 'fetching_market' ? '拉取行情...' : 'AI 思考中...'}
            </div>
          </div>
        )}

        {err && <div className="bg-down-100 text-down-500 text-xs px-3 py-2 rounded">{err}</div>}
      </div>

      <div className="px-3 py-3 border-t border-cream-300">
        {messages.length === 0 && focus?.symbol && (
          <div className="flex gap-1.5 mb-2 flex-wrap">
            {QUICK_PROMPTS.map(q => (
              <button key={q} onClick={() => send(q)} disabled={loading}
                      className="text-xs border border-cream-300 rounded px-2 py-1 text-ink-700 hover:bg-cream-100 disabled:opacity-50">
                {q}
              </button>
            ))}
          </div>
        )}
        <div className="flex gap-2">
          <input type="text"
                 value={draft}
                 onChange={e => setDraft(e.target.value)}
                 onKeyDown={e => e.key === 'Enter' && send(draft)}
                 disabled={loading}
                 placeholder={focus?.symbol ? '问点什么...' : '先在左侧选一只持仓'}
                 className="flex-1 bg-white border border-cream-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-clay-500 text-ink-900 disabled:bg-cream-100" />
          <button onClick={() => send(draft)} disabled={loading || !draft.trim()}
                  className="bg-clay-500 hover:bg-clay-600 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-semibold">
            发送
          </button>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ role, content, streaming }: {
  role: 'user' | 'assistant'; content: string; streaming?: boolean;
}) {
  if (role === 'user') {
    return (
      <div className="flex gap-2 flex-row-reverse">
        <div className="w-6 h-6 rounded-full bg-cream-300 shrink-0 mt-0.5 flex items-center justify-center text-xs text-ink-700">我</div>
        <div className="bg-clay-100 border border-clay-500/40 rounded-lg px-3 py-2 flex-1 text-ink-900 whitespace-pre-wrap">{content}</div>
      </div>
    );
  }
  return (
    <div className="flex gap-2">
      <div className="w-6 h-6 rounded-full bg-clay-500 shrink-0 mt-0.5"></div>
      <div className="bg-cream-100 border border-cream-300 rounded-lg px-3 py-2 flex-1 text-ink-900 whitespace-pre-wrap">
        {content}
        {streaming && <span className="inline-block w-1.5 h-3 bg-clay-500 align-middle ml-1 animate-pulse"></span>}
      </div>
    </div>
  );
}
