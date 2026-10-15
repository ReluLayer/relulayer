import React, { useId, useState } from 'react';
import { Check, FileText } from 'lucide-react';

export default function SbloLeadForm() {
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    organization: '',
    role: 'Defense Prime / Federal Health IT Program Manager',
    customRole: '',
    interest: 'CISA Memory-Safety Audit'
  });

  const nameId = useId();
  const emailId = useId();
  const organizationId = useId();
  const roleId = useId();
  const customRoleId = useId();
  const customRoleDescId = useId();
  const statusId = useId();

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);

    // Simulate form submission
    setTimeout(() => {
      setLoading(false);
      setSubmitted(true);
    }, 600);
  };

  const finalRoleDisplay = formData.role === 'Other' ? (formData.customRole || 'Other') : formData.role;

  return (
    <div className="bg-slate-900 border border-slate-800 p-6 rounded-2xl shadow-xl max-w-xl mx-auto">
      <h3 className="text-lg font-bold text-white mb-1">Prepare Your Program for CISA Memory-Safety Audits</h3>
      <p className="text-xs text-slate-400 mb-4">
        Whether you are a defense Prime Program Manager, a federal Healthcare IT leader, an automotive functional safety lead, or an industrial machinery integrator, request a technical evaluation and compliance briefing today. Direct proposals: <a href="mailto:proposals@atelierlogicgroup.com" className="text-amber-400 underline">proposals@atelierlogicgroup.com</a>.
      </p>

      {submitted ? (
        <div
          className="bg-slate-950 border border-amber-500/30 p-6 rounded-xl text-center"
          aria-live="polite"
          role="status"
          id={statusId}
        >
          <div className="w-12 h-12 bg-amber-500/10 text-amber-400 rounded-full flex items-center justify-center mx-auto mb-3 font-bold text-xl">
            <Check className="h-6 w-6" aria-hidden="true" />
            <span className="sr-only">Success</span>
          </div>
          <h4 className="text-base font-bold text-white mb-1">Inquiry Submitted Successfully</h4>
          <p className="text-xs text-slate-300 mb-4">
            Thank you, {formData.name} ({finalRoleDisplay} at {formData.organization}). Our Principal Architect and engineering team will review your CISA memory-safety request and contact you within 24 business hours.
          </p>
          <a
            href="https://atelierlogicgroup.com/capability-statement/"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs rounded-lg transition shadow-lg"
          >
            <FileText className="h-4 w-4" aria-hidden="true" />
            View & Print Full Capability Statement
          </a>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-3">
          <p className="text-xs text-slate-400 mb-1 flex items-center gap-2">
            <span aria-hidden="true">🔒</span>
            <span>100% On-Shore US Engineering Review | $15,000.00–$25,000.00 Fixed-Fee Audits (50k LOC Cap) | Prepaid T&amp;M Blocks ($375.00/hr) | SLA &lt; 2 Hours</span>
          </p>

          <div>
            <label htmlFor={nameId} className="block text-xs font-semibold text-slate-300 mb-1">Full Name</label>
            <input
              id={nameId}
              type="text"
              required
              autoComplete="name"
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-amber-500"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder="e.g. Jane Doe"
            />
          </div>

          <div>
            <label htmlFor={emailId} className="block text-xs font-semibold text-slate-300 mb-1">Work Email</label>
            <input
              id={emailId}
              type="email"
              required
              autoComplete="email"
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-amber-500"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              placeholder="e.g. jdoe@textron.com"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor={organizationId} className="block text-xs font-semibold text-slate-300 mb-1">Organization / Prime</label>
              <input
                id={organizationId}
                type="text"
                required
                autoComplete="organization"
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-amber-500"
                value={formData.organization}
                onChange={(e) => setFormData({ ...formData, organization: e.target.value })}
                placeholder="e.g. Textron Systems / DoD"
              />
            </div>

            <div>
              <label htmlFor={roleId} className="block text-xs font-semibold text-slate-300 mb-1">Your Role</label>
              <select
                id={roleId}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-amber-500"
                value={formData.role}
                onChange={(e) => setFormData({ ...formData, role: e.target.value })}
              >
                <option value="Power Electronics / Inverter Engineer">Power Electronics / Inverter Engineer</option>
                <option value="Automotive Functional Safety (ASIL-D) Lead">Automotive Functional Safety (ASIL-D) Lead</option>
                <option value="Industrial Machinery & Laser Integrator">Industrial Machinery &amp; Laser Integrator</option>
                <option value="Defense Prime / Federal Health IT Program Manager">Defense Prime / Federal Health IT Program Manager</option>
                <option value="Enterprise / C# .NET Systems Architect">Enterprise / C# .NET Systems Architect</option>
                <option value="EU AI Act & CISA Compliance Audit">EU AI Act &amp; CISA Compliance Audit</option>
                <option value="Contracting Officer">Contracting Officer</option>
                <option value="Other">Other</option>
              </select>
            </div>
          </div>

          {formData.role === 'Other' && (
            <div>
              <label htmlFor={customRoleId} className="block text-xs font-semibold text-amber-400 mb-1">
                Please Specify Your Role
              </label>
              <input
                id={customRoleId}
                type="text"
                required
                aria-describedby={customRoleDescId}
                className="w-full bg-slate-950 border border-amber-500/50 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-amber-500"
                value={formData.customRole}
                onChange={(e) => setFormData({ ...formData, customRole: e.target.value })}
                placeholder="e.g. Health IT Director, Research Lead, Defense Investor"
              />
              <span id={customRoleDescId} className="sr-only">
                Enter your role because Other was selected above.
              </span>
            </div>
          )}

          <p className="text-[11px] text-slate-400 leading-snug">
            By submitting, you agree to our{' '}
            <a href="https://atelierlogicgroup.com/privacy/" className="text-amber-400 underline hover:text-amber-300">
              Privacy Policy
            </a>
            . We will only use your information to respond to this inquiry.
          </p>

          <button
            type="submit"
            disabled={loading}
            aria-busy={loading}
            className="w-full mt-2 py-2.5 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs rounded-lg transition shadow-lg disabled:opacity-50"
          >
            {loading ? 'Processing Inquiry...' : 'Request CISA Audit & SDK Briefing'}
          </button>
        </form>
      )}
    </div>
  );
}
