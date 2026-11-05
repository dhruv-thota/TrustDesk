import React from 'react';

export default function TicketContext({ context, loading, error }) {
  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow border border-gray-200 p-8 text-center text-gray-400 text-sm flex items-center justify-center gap-2">
        <span className="inline-block w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></span>
        Loading ticket context...
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow border border-rose-200 p-6 text-center text-rose-700">
        <p className="text-sm font-medium mb-1">Failed to load ticket context</p>
        <p className="text-xs text-rose-500">{error}</p>
      </div>
    );
  }

  if (!context) {
    return (
      <div className="bg-white rounded-lg shadow border border-gray-200 p-8 text-center text-gray-500 text-sm">
        Select a ticket from the queue to inspect operational context.
      </div>
    );
  }

  const { ticket, customer, order, past_tickets = [] } = context;
  const quarantinedOrderId = ticket?.raw_metadata?.unresolved_order_id;

  return (
    <div className="space-y-4">
      {/* Ticket Details Header & Message */}
      <div className="bg-white rounded-lg shadow border border-gray-200 p-5">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-100 pb-3 mb-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono font-bold text-gray-500">{ticket.ticket_id}</span>
              <span className="text-xs px-2 py-0.5 rounded bg-blue-50 text-blue-700 font-semibold uppercase">
                {ticket.status}
              </span>
            </div>
            <h1 className="text-lg font-bold text-gray-900 mt-1">{ticket.subject}</h1>
          </div>
          <div className="text-right text-xs text-gray-500">
            <div>Created: {new Date(ticket.created_at).toLocaleString()}</div>
          </div>
        </div>

        {/* Customer Inquiry Message */}
        <div className="mt-3">
          <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5">
            Customer Inquiry Message
          </h4>
          <div className="bg-gray-50 border border-gray-200 rounded p-3 text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">
            {ticket.message}
          </div>
        </div>
      </div>

      {/* Grid: Customer Profile & Order Context */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Customer Profile Card */}
        <div className="bg-white rounded-lg shadow border border-gray-200 p-4">
          <h3 className="text-xs font-bold text-gray-700 uppercase tracking-wider border-b border-gray-100 pb-2 mb-3">
            Customer Profile
          </h3>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between">
              <span className="text-gray-500">Customer ID:</span>
              <span className="font-mono font-semibold text-gray-900">{customer?.customer_id}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Name:</span>
              <span className="font-medium text-gray-900">{customer?.name || '—'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Email:</span>
              <span className="text-gray-900">{customer?.email || '—'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Member Since:</span>
              <span className="text-gray-700">
                {customer?.created_at ? new Date(customer.created_at).toLocaleDateString() : '—'}
              </span>
            </div>
          </div>
        </div>

        {/* Order Details Card */}
        <div className="bg-white rounded-lg shadow border border-gray-200 p-4">
          <h3 className="text-xs font-bold text-gray-700 uppercase tracking-wider border-b border-gray-100 pb-2 mb-3">
            Order Context
          </h3>

          {/* Quarantined Order Notice */}
          {quarantinedOrderId && (
            <div className="mb-3 p-2 bg-amber-50 border border-amber-200 rounded text-xs text-amber-800" data-testid="quarantined-order-notice">
              <strong className="font-semibold">Quarantined Order Reference:</strong> {quarantinedOrderId} (Unresolvable in order database)
            </div>
          )}

          {!order ? (
            <div className="p-4 text-center text-xs text-gray-500 bg-gray-50 rounded border border-dashed border-gray-200" data-testid="no-order-linked">
              No Order Linked to Ticket
            </div>
          ) : (
            <div className="space-y-3">
              <div className="space-y-1.5 text-xs">
                <div className="flex justify-between">
                  <span className="text-gray-500">Order ID:</span>
                  <span className="font-mono font-semibold text-gray-900">{order.order_id}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Status:</span>
                  <span className="font-medium text-gray-800 capitalize">{order.status || '—'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Order Date:</span>
                  <span className="text-gray-700">
                    {order.order_date ? new Date(order.order_date).toLocaleDateString() : '—'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Delivery Date:</span>
                  <span className="font-medium text-gray-900">
                    {order.delivery_date ? new Date(order.delivery_date).toLocaleDateString() : 'Pending / Not Delivered'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Total Amount:</span>
                  <span className="font-bold text-gray-900">
                    ${Number(order.total_amount || 0).toFixed(2)}
                  </span>
                </div>
              </div>

              {/* Items Table */}
              {Array.isArray(order.items) && order.items.length > 0 && (
                <div className="mt-2 border-t border-gray-100 pt-2">
                  <span className="text-[11px] font-semibold text-gray-600 block mb-1">Purchased Items:</span>
                  <div className="max-h-32 overflow-y-auto border border-gray-100 rounded text-xs">
                    <table className="w-full text-left">
                      <thead className="bg-gray-50 text-[10px] text-gray-500 uppercase">
                        <tr>
                          <th className="py-1 px-2">SKU</th>
                          <th className="py-1 px-2">Name</th>
                          <th className="py-1 px-2 text-right">Qty</th>
                          <th className="py-1 px-2 text-right">Price</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {order.items.map((it, idx) => (
                          <tr key={it.sku || idx}>
                            <td className="py-1 px-2 font-mono text-gray-600">{it.sku || '—'}</td>
                            <td className="py-1 px-2 text-gray-800">{it.name || '—'}</td>
                            <td className="py-1 px-2 text-right text-gray-600">{it.qty ?? 1}</td>
                            <td className="py-1 px-2 text-right font-medium text-gray-900">
                              ${Number(it.price || 0).toFixed(2)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Customer Ticket History */}
      <div className="bg-white rounded-lg shadow border border-gray-200 p-4">
        <h3 className="text-xs font-bold text-gray-700 uppercase tracking-wider border-b border-gray-100 pb-2 mb-3">
          Customer Past Tickets History ({past_tickets.length})
        </h3>
        {past_tickets.length === 0 ? (
          <div className="p-3 text-center text-xs text-gray-500 bg-gray-50 rounded" data-testid="empty-past-tickets">
            No previous support tickets for this customer.
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {past_tickets.map((pt) => (
              <div key={pt.ticket_id} className="py-2 flex items-center justify-between text-xs">
                <div>
                  <span className="font-mono font-medium text-gray-800 mr-2">{pt.ticket_id}</span>
                  <span className="text-gray-700">{pt.subject}</span>
                </div>
                <div className="flex items-center space-x-2">
                  <span className="text-[11px] text-gray-500">
                    {new Date(pt.created_at).toLocaleDateString()}
                  </span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-700 uppercase font-semibold">
                    {pt.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

