import {
  getProviderConfigConfigProvidersGet,
  providerReadinessConfigProvidersReadinessGet,
  setupSubmitSetupPost,
  setupStatusSetupStatusGet,
  updateProviderConfigConfigProvidersPut,
  type SetupSubmitRequest,
} from "./generated";

export const loadProviderConfig = getProviderConfigConfigProvidersGet;
export const loadProviderReadiness =
  providerReadinessConfigProvidersReadinessGet;
export const loadSetupStatus = setupStatusSetupStatusGet;
export const updateProviderConfig = updateProviderConfigConfigProvidersPut;

export function saveInitialSetup(request: SetupSubmitRequest) {
  return setupSubmitSetupPost(request);
}
