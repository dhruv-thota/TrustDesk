import React, { useState, useEffect } from 'react';
import { getDemoToken, setDemoToken, clearDemoToken } from '../api/client';

export default function DemoSessionBar({ onSessionChange, authErrorAlert = null }) {
  const [tokenInput, setTokenInput] = useState('');
  const [hasToken, setHasToken] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);

  useEffect(() => {
    const current = getDemoToken();
    setHasToken(Boolean(current));
    if (current) {
      setTokenInput(current);
    }
  }, []);

  useEffect(() => {
    if (authErrorAlert) {
      setErrorMsg(authErrorAlert);
      setIsOpen(true);
      setHasToken(false);
    }
  }, [authErrorAlert]);

  const handleSave = (e) => {
    e?.preventDefault();
    if (!tokenInput.trim()) {
      setErrorMsg('Please enter a valid demo bearer token.');
      return;
    }
    setDemoToken(tokenInput.trim());
    setHasToken(true);
    setErrorMsg(null);
    setIsOpen(false);
    if (onSessionChange) onSessionChange(tokenInput.trim());
  };

  const handleClear = () => {
    clearDemoToken();
    setTokenInput('');
    setHasToken(false);
    setErrorMsg(null);
    setIsOpen(true);
    if (onSessionChange) onSessionChange(null);
  };

  return (
    <header className="bg-slate-900 text-white shadow-md">
      <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <span className="font-bold text-lg tracking-tight text-white flex items-center gap-2">
            <span className="inline-block w-3 h-3 rounded-full bg-blue-500"></span>
            TrustDesk
          </span>
          <span className="text-xs font-semibold px-2.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
            Support-Agent Dashboard
          </span>
        </div>

        <div className="flex items-center space-x-3 text-sm">
          <div className="flex items-center space-x-2">
            <span
              data-testid="session-status-indicator"
              className={`inline-block w-2.5 h-2.5 rounded-full ${
                hasToken ? 'bg-emerald-400' : 'bg-rose-400 animate-pulse'
              }`}
            />
            <span className="text-xs text-slate-300 font-medium">
              {hasToken ? 'Demo Session Active' : 'Unauthenticated'}
            </span>
          </div>

          {hasToken ? (
            <div className="flex items-center space-x-2">
              <button
                type="button"
                onClick={() => setIsOpen(!isOpen)}
                className="px-2.5 py-1 text-xs rounded bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition"
              >
                Change Token
              </button>
              <button
                type="button"
                onClick={handleClear}
                className="px-2.5 py-1 text-xs rounded bg-rose-600/80 hover:bg-rose-600 text-white transition"
              >
                Clear Session
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setIsOpen(true)}
              className="px-3 py-1 text-xs font-medium rounded bg-blue-600 hover:bg-blue-500 text-white shadow transition"
            >
              Set Demo Token
            </button>
          )}
        </div>
      </div>

      {/* Token Modal / Dropdown */}
      {isOpen && (
        <div className="bg-slate-800 border-t border-slate-700 px-4 py-3 transition-all">
          <div className="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div className="text-xs text-slate-300">
              <span className="font-semibold text-white">Local Demo Session:</span> Enter the bearer token from your server environment (stored strictly in browser <code className="bg-slate-900 px-1 py-0.5 rounded text-blue-300">sessionStorage</code>).
            </div>

            <form onSubmit={handleSave} className="flex flex-wrap items-center gap-2">
              <input
                type="password"
                aria-label="Demo Bearer Token"
                placeholder="Bearer token..."
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                className="px-3 py-1.5 text-xs bg-slate-900 border border-slate-600 rounded text-white focus:outline-none focus:ring-1 focus:ring-blue-500 w-64"
              />
              <button
                type="submit"
                className="px-3 py-1.5 text-xs font-medium rounded bg-blue-600 hover:bg-blue-500 text-white transition"
              >
                Save Token
              </button>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="px-2 py-1.5 text-xs text-slate-400 hover:text-white"
              >
                Close
              </button>
            </form>
          </div>

          {errorMsg && (
            <div className="max-w-7xl mx-auto mt-2 text-xs text-rose-300 bg-rose-950/50 border border-rose-800 rounded px-2.5 py-1">
              {errorMsg}
            </div>
          )}
        </div>
      )}
    </header>
  );
}
