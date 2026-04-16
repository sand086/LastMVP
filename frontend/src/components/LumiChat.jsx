import React, { useState, useRef, useEffect, useCallback } from 'react';
import DOMPurify from 'dompurify';
import { sendLumiMessage } from '../lib/api';
import api from '../lib/api';
import { X, Send } from 'lucide-react';

const TruckSVG = ({ size = 28 }) => (
    <svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" width={size} height={size}>
        <rect x="4" y="18" width="24" height="18" rx="3" fill="#fff" opacity=".95"/>
        <rect x="7" y="11" width="18" height="9" rx="2" fill="#fff" opacity=".85"/>
        <rect x="9" y="13" width="13" height="6" rx="1.5" fill="#93C5FD" opacity=".9"/>
        <rect x="28" y="14" width="16" height="22" rx="2" fill="#fff" opacity=".9"/>
        <line x1="28" y1="24" x2="44" y2="24" stroke="#E2E0DB" strokeWidth="1.2"/>
        <circle cx="11" cy="37" r="4.5" fill="#374151"/>
        <circle cx="11" cy="37" r="2" fill="#6B7280"/>
        <circle cx="35" cy="37" r="4.5" fill="#374151"/>
        <circle cx="35" cy="37" r="2" fill="#6B7280"/>
        <rect x="4" y="22" width="3" height="2.5" rx="1" fill="#FDE68A" opacity=".95"/>
        <line x1="4" y1="18" x2="7" y2="11" stroke="#fff" strokeWidth="1.5" opacity=".6"/>
        <line x1="18" y1="18" x2="18" y2="36" stroke="#E2E0DB" strokeWidth="1" opacity=".6"/>
        <rect x="19" y="26" width="3" height="1.5" rx=".75" fill="#9CA3AF" opacity=".7"/>
    </svg>
);

function formatAIText(text) {
    const html = text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/`([^`]+)`/g, '<code style="background:#F0EFEC;padding:1px 4px;border-radius:3px;font-size:12px">$1</code>')
        .replace(/\n/g, '<br>')
        .replace(/(\d+\.?\d*%)/g, '<strong style="color:#1A1916">$1</strong>');
    return DOMPurify.sanitize(html, { ALLOWED_TAGS: ['strong', 'code', 'br', 'em', 'p'], ALLOWED_ATTR: ['style'] });
}

const WELCOME_MSG = {
    role: 'assistant',
    content: 'Hola, soy **Lumi**, tu asistente de inteligencia operacional. Puedo ayudarte con datos de entregas, SLA, drivers, incidencias y calidad de evidencias del periodo activo.',
};

const QUICK_ACTIONS = [
    { label: 'SLA actual', icon: '📊' },
    { label: 'Drivers criticos', icon: '⚠️' },
    { label: 'Evidencias', icon: '📸' },
    { label: 'Incidencias', icon: '🚨' },
];

const LumiChat = ({ period = '7d', clientId, providerId, journeyId }) => {
    const [open, setOpen] = useState(false);
    const [messages, setMessages] = useState([WELCOME_MSG]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [showBadge, setShowBadge] = useState(false);
    const [activeContext, setActiveContext] = useState(null);
    const scrollRef = useRef(null);
    const inputRef = useRef(null);

    useEffect(() => {
        const timer = setTimeout(() => { if (!open) setShowBadge(true); }, 3000);
        return () => clearTimeout(timer);
    }, [open]);

    useEffect(() => {
        if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }, [messages, loading]);

    useEffect(() => {
        if (open && inputRef.current) inputRef.current.focus();
    }, [open]);

    // Fetch active journey context when journeyId changes
    useEffect(() => {
        if (journeyId) {
            api.get(`/lumi/active-context?journey_id=${journeyId}`)
                .then(res => setActiveContext(res.data))
                .catch(() => setActiveContext(null));
        } else {
            setActiveContext(null);
        }
    }, [journeyId]);

    const handleOpen = () => { setOpen(true); setShowBadge(false); };

    const sendMsg = useCallback(async (text) => {
        if (!text.trim() || loading) return;
        const userMsg = { role: 'user', content: text.trim() };
        setMessages(prev => [...prev, userMsg]);
        setInput('');
        setLoading(true);

        try {
            const history = messages.filter(m => m !== WELCOME_MSG).map(m => ({ role: m.role, content: m.content }));
            const res = await sendLumiMessage({
                message: text.trim(),
                history: history.slice(-12),
                period,
                client_id: clientId || undefined,
                provider_id: providerId || undefined,
                journey_id: journeyId || undefined,
            });
            setMessages(prev => [...prev, { role: 'assistant', content: res.data.reply }]);
        } catch {
            setMessages(prev => [...prev, { role: 'assistant', content: 'Hubo un problema de conexion. Intenta de nuevo.' }]);
        } finally {
            setLoading(false);
        }
    }, [loading, messages, period, clientId, providerId, journeyId]);

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMsg(input); }
    };

    return (
        <>
            <style>{`
                .lumi-fab { position: fixed; bottom: 28px; right: 28px; z-index: 900; width: 56px; height: 56px; border-radius: 50%; background: #1A1916; border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 20px rgba(0,0,0,0.25); transition: transform 0.2s; }
                .lumi-fab:hover { transform: scale(1.05); }
                .lumi-badge { position: absolute; top: -2px; right: -2px; width: 14px; height: 14px; border-radius: 50%; background: #DC2626; border: 2px solid #fff; }
                .lumi-panel { position: fixed; bottom: 94px; right: 28px; z-index: 901; width: 380px; max-height: 600px; background: #fff; border: 1px solid #E2E0DB; border-radius: 12px; box-shadow: 0 8px 32px rgba(0,0,0,0.15); display: flex; flex-direction: column; animation: lumiSlideUp 0.2s ease-out; overflow: hidden; }
                @keyframes lumiSlideUp { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
                .lumi-header { background: #1A1916; color: #fff; padding: 14px 16px; display: flex; align-items: center; gap: 10px; }
                .lumi-messages { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; max-height: 400px; min-height: 200px; }
                .lumi-bubble { max-width: 85%; padding: 10px 14px; border-radius: 12px; font-size: 13px; line-height: 1.55; word-break: break-word; }
                .lumi-bubble-user { align-self: flex-end; background: #1A1916; color: #fff; border-bottom-right-radius: 3px; }
                .lumi-bubble-ai { align-self: flex-start; background: #F0EFEC; border: 1px solid #E2E0DB; color: #1A1916; border-bottom-left-radius: 3px; }
                .lumi-bubble-ai strong { font-weight: 600; }
                .lumi-input-area { border-top: 1px solid #E2E0DB; padding: 12px 16px; display: flex; align-items: flex-end; gap: 8px; }
                .lumi-textarea { flex: 1; border: none; outline: none; font-size: 13px; font-family: 'DM Sans', sans-serif; resize: none; max-height: 80px; color: #1A1916; background: transparent; }
                .lumi-textarea::placeholder { color: #9C9A92; }
                .lumi-send { width: 34px; height: 34px; border-radius: 50%; background: #1A1916; border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; flex-shrink: 0; transition: opacity 0.15s; }
                .lumi-send:disabled { opacity: 0.4; cursor: default; }
                .lumi-typing { display: flex; gap: 4px; padding: 10px 14px; align-self: flex-start; }
                .lumi-typing span { width: 6px; height: 6px; border-radius: 50%; background: #9C9A92; animation: lumiBounce 1.4s infinite ease-in-out; }
                .lumi-typing span:nth-child(2) { animation-delay: 0.2s; }
                .lumi-typing span:nth-child(3) { animation-delay: 0.4s; }
                @keyframes lumiBounce { 0%,80%,100% { transform: translateY(0); } 40% { transform: translateY(-6px); } }
                .lumi-quick { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
                .lumi-quick-btn { padding: 5px 10px; border: 1px solid #E2E0DB; border-radius: 6px; font-size: 12px; font-family: 'DM Sans', sans-serif; background: #fff; cursor: pointer; color: #1A1916; transition: background 0.15s, border-color 0.15s; }
                .lumi-quick-btn:hover { background: #F0EFEC; border-color: #C8C6BF; }
                .lumi-footer { text-align: center; padding: 6px 16px 10px; font-size: 11px; color: #9C9A92; }
                .lumi-ctx-badge { display: flex; align-items: center; gap: 6px; padding: 4px 10px; margin: 0 16px 4px; border-radius: 6px; background: #EFF6FF; border: 1px solid #BFDBFE; font-size: 11px; color: #1D4ED8; }
            `}</style>

            {!open && (
                <button className="lumi-fab" onClick={handleOpen} data-testid="lumi-fab">
                    <TruckSVG size={28} />
                    {showBadge && <div className="lumi-badge" />}
                </button>
            )}

            {open && (
                <div className="lumi-panel" data-testid="lumi-panel">
                    <div className="lumi-header">
                        <div style={{ width: 30, height: 30, borderRadius: '50%', background: '#2A2A27', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            <TruckSVG size={22} />
                        </div>
                        <div style={{ flex: 1 }}>
                            <div style={{ fontWeight: 600, fontSize: 14 }}>Lumi — Asistente LastMile</div>
                            <div style={{ fontSize: 11, opacity: 0.7, display: 'flex', alignItems: 'center', gap: 4 }}>
                                <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#4ADE80' }} />
                                Conectado
                            </div>
                        </div>
                        <button onClick={() => setOpen(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#fff', opacity: 0.7, padding: 4 }} data-testid="lumi-close">
                            <X size={18} />
                        </button>
                    </div>

                    {/* Active context indicator */}
                    {activeContext && (
                        <div className="lumi-ctx-badge" data-testid="lumi-active-context">
                            <span style={{ fontSize: 13 }}>📍</span>
                            Contexto activo: Ruta {activeContext.journey_code}
                        </div>
                    )}

                    <div className="lumi-messages" ref={scrollRef}>
                        {messages.map((msg, i) => (
                            <div key={`msg-${msg.role}-${i}-${msg.content?.slice(0,12)}`}>
                                <div className={`lumi-bubble ${msg.role === 'user' ? 'lumi-bubble-user' : 'lumi-bubble-ai'}`}
                                    dangerouslySetInnerHTML={{ __html: formatAIText(msg.content) }}
                                />
                                {i === 0 && msg.role === 'assistant' && (
                                    <div className="lumi-quick">
                                        {QUICK_ACTIONS.map(qa => (
                                            <button key={qa.label} className="lumi-quick-btn" onClick={() => sendMsg(`¿Cual es el ${qa.label.toLowerCase()} del periodo?`)} data-testid={`lumi-qa-${qa.label.toLowerCase().replace(/\s/g,'-')}`}>
                                                {qa.icon} {qa.label}
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </div>
                        ))}
                        {loading && (
                            <div className="lumi-typing"><span /><span /><span /></div>
                        )}
                    </div>

                    <div className="lumi-input-area">
                        <textarea
                            ref={inputRef}
                            className="lumi-textarea"
                            value={input}
                            onChange={e => setInput(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder={activeContext ? `Pregunta sobre ${activeContext.journey_code}...` : 'Escribe tu pregunta...'}
                            rows={1}
                            data-testid="lumi-input"
                        />
                        <button className="lumi-send" onClick={() => sendMsg(input)} disabled={!input.trim() || loading} data-testid="lumi-send">
                            <Send size={15} color="#fff" />
                        </button>
                    </div>
                    <div className="lumi-footer">
                        {activeContext ? `Ruta ${activeContext.journey_code} · Datos en vivo` : 'Lumi usa los datos del reporte activo'} · Powered by Claude
                    </div>
                </div>
            )}
        </>
    );
};

export default LumiChat;
