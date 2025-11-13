from flask.sessions import SecureCookieSessionInterface

class CustomSessionInterface(SecureCookieSessionInterface):
    def get_max_age(self, app):
        if app.permanent_session_lifetime is not None:
            return int(app.permanent_session_lifetime.total_seconds())
        return None

    def save_session(self, app, session, response):
        if response is None:
            return

        domain = self.get_cookie_domain(app)
        path = self.get_cookie_path(app)

        # Check if the session should be deleted
        if not session:
            if session.modified:
                response.delete_cookie(
                    app.config['SESSION_COOKIE_NAME'],
                    domain=domain,
                    path=path
                )
            return

        # Get cookie settings without the 'partitioned' parameter
        httponly = self.get_cookie_httponly(app)
        secure = self.get_cookie_secure(app)
        samesite = self.get_cookie_samesite(app)
        max_age = self.get_max_age(app)

        # Set the cookie with proper parameters
        response.set_cookie(
            app.config['SESSION_COOKIE_NAME'],
            self.get_signing_serializer(app).dumps(dict(session)),
            httponly=httponly,
            secure=secure,
            max_age=max_age,
            domain=domain,
            path=path,
            samesite=samesite
        )
