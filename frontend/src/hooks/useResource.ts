import { useCallback, useEffect, useState } from "react";

export type Resource<T> =
  | { state: "loading" }
  | { state: "error"; error: Error }
  | { state: "ready"; data: T };

/** Load one thing on mount. `reload()` fetches again without clearing the
 * current data, so the page doesn't flash back to a spinner. `set()`
 * replaces the data when the caller already knows the answer. */
export function useResource<T>(
  load: () => Promise<T>,
): Resource<T> & { reload: () => void; set: (data: T) => void } {
  const [resource, setResource] = useState<Resource<T>>({ state: "loading" });
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    load().then(
      (data) => !cancelled && setResource({ state: "ready", data }),
      (error: Error) => !cancelled && setResource({ state: "error", error }),
    );
    return () => {
      cancelled = true;
    };
    // `load` must be stable: a module-level function, or useCallback with
    // its inputs (e.g. a route id), so a new id loads again.
  }, [load, version]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  const set = useCallback((data: T) => setResource({ state: "ready", data }), []);
  return { ...resource, reload, set };
}
