#
#  GoogleFindMyTools - A set of tools to interact with the Google Find My API
#  Copyright © 2024 Leon Böttger. All rights reserved.
#

import gpsoauth

from Auth.aas_token_retrieval import get_aas_token
from Auth.fcm_receiver import FcmReceiver
from Auth.token_cache import delete_cached_value


def request_token(username, scope, play_services = False):

    aas_token = get_aas_token()
    android_id = FcmReceiver().get_android_id()
    request_app = 'com.google.android.gms' if play_services else 'com.google.android.apps.adm'

    auth_response = gpsoauth.perform_oauth(
        username, aas_token, android_id,
        service='oauth2:https://www.googleapis.com/auth/' + scope,
        app=request_app,
        client_sig='38918a453d07199354f8b19af05ec6562ced5788')

    if 'Auth' not in auth_response:
        # Controleer of het echt een verlopen sessie is (Error=NeedsBrowser/BadAuthentication)
        # of een tijdelijke fout. Wis het token alleen bij echte auth-fouten.
        err = auth_response.get('Error', '')
        if err in ('NeedsBrowser', 'BadAuthentication', 'TokenExpired', 'InvalidCredentials'):
            delete_cached_value('aas_token')
        raise RuntimeError(
            "Google-sessie verlopen. "
            "Herverbind je account via de webapp -> Google Auth -> Login."
        )

    return auth_response['Auth']