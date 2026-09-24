/**
 * Button slot for Chrome's customizable select (`appearance: base-select`).
 *
 * Place it as the first child of a `.select` element. Chrome otherwise
 * generates the slot in its own shadow tree, where the ellipsis daisyUI sets
 * on `selectedcontent` cannot reach it, so a long label runs under the arrow.
 * Browsers without customizable select lay the button out as `display:
 * contents` and render nothing extra.
 */
export function SelectedLabel() {
  return (
    <button type="button">
      <selectedcontent />
    </button>
  );
}
