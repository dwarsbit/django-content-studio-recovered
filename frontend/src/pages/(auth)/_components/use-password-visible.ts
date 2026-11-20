import { useState } from "react";

/** The visibility of a page's password fields, which they share. */
export function usePasswordVisible() {
  const [visible, setVisible] = useState(false);

  return [visible, () => setVisible((current) => !current)] as const;
}
