import { PlusCircle } from 'lucide-react';

/**
 * TECH-39: the single "Add Channel" deep-link CTA (blueprint §2).
 *
 * Renders the anchor to https://t.me/IndexGebeyaBot?start=addchannel with
 * target="_blank" / rel="noopener noreferrer". Only the ANCHOR is shared —
 * the surrounding cards differ per site and stay inline.
 *
 * Props:
 * - label: string, default "Add Channel" — also the accessible name
 * - className: string, optional override of the anchor's classes
 */
const AddChannelButton = ({ label = 'Add Channel', className }) => (
  <a
    href="https://t.me/IndexGebeyaBot?start=addchannel"
    target="_blank"
    rel="noopener noreferrer"
    className={className ?? 'flex items-center gap-1.5 px-3 py-2 bg-brand-600 text-white rounded-xl text-xs font-medium hover:bg-brand-700 transition-colors shrink-0'}
  >
    <PlusCircle size={14} />
    {label}
  </a>
);

export default AddChannelButton;
