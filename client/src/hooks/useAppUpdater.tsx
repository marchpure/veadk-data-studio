import { useState, useEffect, useRef } from 'react';
import { check, type Update } from '@tauri-apps/plugin-updater';
import { relaunch } from '@tauri-apps/plugin-process';

interface UpdateState {
  available: boolean;
  update: Update | null;
  checking: boolean;
  downloading: boolean;
  error: string | null;
  dismissed: boolean;
}

export const useAppUpdater = () => {
  const [state, setState] = useState<UpdateState>({
    available: false,
    update: null,
    checking: true,
    downloading: false,
    error: null,
    dismissed: false,
  });

  // Use ref to track dismissed state for interval callback (avoids stale closure)
  const dismissedRef = useRef(false);

  useEffect(() => {
    checkForUpdates();

    const interval = setInterval(() => {
      // Skip check if user already dismissed the update notification
      if (dismissedRef.current) return;
      checkForUpdates();
    }, 60000); // Check every 1 minute

    return () => clearInterval(interval);
  }, []);

  const checkForUpdates = async () => {
    // Skip if user already dismissed an update notification
    if (dismissedRef.current) return;

    // Skip if not running in Tauri (e.g., browser/Docker mode)
    if (!('__TAURI_INTERNALS__' in window)) {
      setState(prev => ({ ...prev, checking: false }));
      return;
    }

    try {
      setState(prev => ({ ...prev, checking: true, error: null }));

      const update = await check();

      // check() returns null if already on latest version, Update object if new version exists
      if (update) {
        console.log(
          `Update available: ${update.version} from ${update.date} with notes: ${update.body}`
        );
        setState(prev => ({
          ...prev,
          available: true,
          update,
          checking: false,
        }));
      } else {
        console.log('No updates available');
        setState(prev => ({
          ...prev,
          available: false,
          update: null,
          checking: false,
        }));
      }
    } catch (error) {
      console.error('Failed to check for updates:', error);
      setState(prev => ({
        ...prev,
        checking: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      }));
    }
  };

  const installUpdate = async () => {
    if (!state.update) return;

    try {
      setState(prev => ({ ...prev, downloading: true, error: null }));

      console.log('Downloading and installing update...');

      await state.update.downloadAndInstall();

      console.log('Update installed, relaunching app...');

      // Relaunch the app after installation
      await relaunch();
    } catch (error) {
      console.error('Failed to install update:', error);
      setState(prev => ({
        ...prev,
        downloading: false,
        error: error instanceof Error ? error.message : 'Failed to install update',
      }));
    }
  };

  const dismissUpdate = () => {
    dismissedRef.current = true;
    setState(prev => ({
      ...prev,
      available: false,
      update: null,
      dismissed: true,
    }));
  };

  return {
    ...state,
    installUpdate,
    dismissUpdate,
    checkForUpdates,
  };
};
