// NB-49: ops console auth state — {user, role, loading, login, logout}.
// On mount, /ops/auth/me resolves the session; 401 (or the
// 'ops:unauthorized' event from any section's opsFetch) -> login state.

import { useCallback, useEffect, useState } from 'react';
import { opsFetch } from '../utils/opsApi';

export function useOpsAuth() {
  const [user, setUser] = useState(null);
  const [role, setRole] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    const onUnauthorized = () => {
      if (mounted) {
        setUser(null);
        setRole(null);
      }
    };
    window.addEventListener('ops:unauthorized', onUnauthorized);

    opsFetch('/ops/auth/me')
      .then((data) => {
        if (mounted) {
          setUser(data.user);
          setRole(data.role);
        }
      })
      .catch(() => {
        if (mounted) {
          setUser(null);
          setRole(null);
        }
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });

    return () => {
      mounted = false;
      window.removeEventListener('ops:unauthorized', onUnauthorized);
    };
  }, []);

  const login = useCallback(async (username, password) => {
    const data = await opsFetch('/ops/auth/login', {
      method: 'POST',
      body: { username, password },
    });
    setUser(data.user);
    setRole(data.role);
    return data;
  }, []);

  const logout = useCallback(async () => {
    try {
      await opsFetch('/ops/auth/logout', { method: 'POST' });
    } catch {
      // session may already be dead — local state flip is what matters
    }
    setUser(null);
    setRole(null);
  }, []);

  return { user, role, loading, login, logout };
}
