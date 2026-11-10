import {
  AuthenticationDetails,
  CognitoUser,
  CognitoUserPool,
  CognitoUserSession,
} from 'amazon-cognito-identity-js';
import { getConfig } from './config';

let pool: CognitoUserPool | null = null;

function userPool(): CognitoUserPool {
  if (!pool) {
    const c = getConfig();
    pool = new CognitoUserPool({ UserPoolId: c.userPoolId, ClientId: c.userPoolClientId });
  }
  return pool;
}

export function signIn(email: string, password: string): Promise<CognitoUserSession> {
  const user = new CognitoUser({ Username: email, Pool: userPool() });
  return new Promise((resolve, reject) => {
    user.authenticateUser(new AuthenticationDetails({ Username: email, Password: password }), {
      onSuccess: resolve,
      onFailure: reject,
      newPasswordRequired: () =>
        reject(new Error('This account needs a new password. Set one with scripts/create_user.py.')),
    });
  });
}

/** Returns a fresh ID token (the SDK refreshes it automatically), or null when signed out. */
export function idToken(): Promise<string | null> {
  if (getConfig().demo) return Promise.resolve('demo');
  const user = userPool().getCurrentUser();
  if (!user) return Promise.resolve(null);
  return new Promise((resolve) => {
    user.getSession((err: Error | null, session: CognitoUserSession | null) => {
      resolve(err || !session?.isValid() ? null : session.getIdToken().getJwtToken());
    });
  });
}

export function currentEmail(): string | null {
  if (getConfig().demo) return 'demo@triageops.dev';
  return userPool().getCurrentUser()?.getUsername() ?? null;
}

export function signOut(): void {
  if (!getConfig().demo) userPool().getCurrentUser()?.signOut();
}
