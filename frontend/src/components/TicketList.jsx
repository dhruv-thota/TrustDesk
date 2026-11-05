import React, { useState, useEffect } from 'react';
import { fetchTickets } from '../api/client';

export default function TicketList({ selectedTicketId, onSelectTicket, refreshTrigger }) {
  const [tickets, setTickets] = useState([]);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const pageSize = 10;

  const loadTickets = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchTickets({
        status: statusFilter || null,
        limit: pageSize,
        offset: page * pageSize,
      });
      setTickets(data.items || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(err.message || 'Failed to load tickets.');
      setTickets([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTickets();
  }, [statusFilter, page, refreshTrigger]);

  const handleFilterChange = (newStatus) => {
    setStatusFilter(newStatus);
    setPage(0);
  };

  const totalPages = Math.ceil(total / pageSize);

  const getStatusBadge = (status) => {
    const s = (status || '').toLowerCase();
    switch (s) {
      case 'open':
        return <span className="px-2 py-0.5 text-xs font-semibold rounded bg-blue-100 text-blue-800">open</span>;
      case 'pending':
        return <span className="px-2 py-0.5 text-xs font-semibold rounded bg-amber-100 text-amber-800">pending</span>;
      case 'closed':
        return <span className="px-2 py-0.5 text-xs font-semibold rounded bg-gray-100 text-gray-700">closed</span>;
      default:
        return <span className="px-2 py-0.5 text-xs font-semibold rounded bg-slate-100 text-slate-800">{status}</span>;
    }
  };

  return (
    <div className="bg-white rounded-lg shadow border border-gray-200 flex flex-col h-full">
      {/* Header and Filter */}
      <div className="p-4 border-b border-gray-200">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-bold text-gray-900 flex items-center gap-2">
            Ticket Queue
            <span className="text-xs font-normal text-gray-500">({total} total)</span>
          </h2>
          <button
            type="button"
            onClick={loadTickets}
            disabled={loading}
            className="text-xs text-blue-600 hover:text-blue-800 font-medium disabled:opacity-50"
          >
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>

        {/* Status Filters */}
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Status filter">
          {['', 'open', 'pending', 'closed'].map((filterVal) => {
            const label = filterVal === '' ? 'All' : filterVal.charAt(0).toUpperCase() + filterVal.slice(1);
            const active = statusFilter === filterVal;
            return (
              <button
                key={filterVal}
                type="button"
                onClick={() => handleFilterChange(filterVal)}
                className={`px-2.5 py-1 text-xs font-medium rounded transition ${
                  active
                    ? 'bg-blue-600 text-white shadow-sm'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Ticket List View */}
      <div className="flex-1 overflow-y-auto divide-y divide-gray-100 min-h-[300px]">
        {loading && (
          <div className="p-8 text-center text-gray-400 text-sm flex items-center justify-center gap-2">
            <span className="inline-block w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></span>
            Loading tickets...
          </div>
        )}

        {!loading && error && (
          <div className="p-6 text-center">
            <p className="text-sm text-rose-600 mb-2">{error}</p>
            <button
              type="button"
              onClick={loadTickets}
              className="text-xs text-blue-600 underline font-medium hover:text-blue-800"
            >
              Try again
            </button>
          </div>
        )}

        {!loading && !error && tickets.length === 0 && (
          <div className="p-8 text-center" data-testid="empty-ticket-state">
            <p className="text-sm text-gray-500 mb-2">No tickets match the selected status filter.</p>
            {statusFilter && (
              <button
                type="button"
                onClick={() => handleFilterChange('')}
                className="text-xs px-2.5 py-1 bg-gray-100 text-gray-700 rounded hover:bg-gray-200 font-medium"
              >
                Clear Filter
              </button>
            )}
          </div>
        )}

        {!loading && !error && tickets.map((t) => {
          const isSelected = selectedTicketId === t.ticket_id;
          return (
            <div
              key={t.ticket_id}
              role="button"
              tabIndex={0}
              onClick={() => onSelectTicket(t.ticket_id)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onSelectTicket(t.ticket_id); }}
              className={`p-3.5 cursor-pointer transition text-left ${
                isSelected
                  ? 'bg-blue-50/80 border-l-4 border-blue-600'
                  : 'hover:bg-gray-50'
              }`}
            >
              <div className="flex items-center justify-between gap-2 mb-1">
                <span className="text-xs font-mono font-semibold text-gray-900">
                  {t.ticket_id}
                </span>
                {getStatusBadge(t.status)}
              </div>

              <h3 className="text-sm font-medium text-gray-900 line-clamp-1 mb-1">
                {t.subject}
              </h3>

              <div className="flex items-center justify-between text-[11px] text-gray-500">
                <span>Customer: <strong className="font-medium text-gray-700">{t.customer_id}</strong></span>
                <span>{new Date(t.created_at).toLocaleDateString()}</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Pagination Footer */}
      {totalPages > 1 && (
        <div className="p-3 border-t border-gray-200 flex items-center justify-between text-xs text-gray-600 bg-gray-50 rounded-b-lg">
          <span>
            Page {page + 1} of {totalPages}
          </span>
          <div className="flex items-center space-x-1">
            <button
              type="button"
              disabled={page === 0 || loading}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              className="px-2 py-1 rounded bg-white border border-gray-300 disabled:opacity-40 hover:bg-gray-100 font-medium"
            >
              Previous
            </button>
            <button
              type="button"
              disabled={page >= totalPages - 1 || loading}
              onClick={() => setPage((p) => p + 1)}
              className="px-2 py-1 rounded bg-white border border-gray-300 disabled:opacity-40 hover:bg-gray-100 font-medium"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

