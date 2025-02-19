# -*- coding: utf-8 -*-

import datetime
import dateutil.relativedelta
import email.header
import email.mime
import email.mime.text
import email.utils
import http.client
import random
import smtplib

from . import skeleton as _skeleton
from ..ext.decorator.session import Session as _deco_Session
from ..ext.paramed_cgi import Handler as paramed_cgi_Handler
from ..ext.paramed_cgi import HandlerError as paramed_cgi_HandlerError
from ...module import mongo as mod_mongo
from ...module.mongo import user as mod_mongo_user
from ...module.mongo import card as mod_mongo_card
from ...module.template import filesystem as mod_tmpl_fs
from ... import config


class HandlerError(paramed_cgi_HandlerError):
    pass


class Handler(paramed_cgi_Handler):
    def handle_post(self):
        req_session = self.req.context.session
        user_id = req_session.get('user_id')
        if user_id is not None:
            self.req.setResponseCode(http.client.NOT_MODIFIED, http.client.responses[http.client.NOT_MODIFIED])
            self.req.setHeader('Cache-Control', 'public, no-cache')
            self.req.setHeader('Content-Type', 'text/plain; charset=utf-8')
            self.req.write('Already authenticated')
            return

        try:
            param_email = self.cgi_params.param_post('email')
        except self.cgi_params.NotFoundError:
            param_email = None
        if param_email is not None:
            session_email = req_session.get('email')
            if session_email is not None:
                if param_email == session_email:
                    self.req.setResponseCode(http.client.NOT_MODIFIED, http.client.responses[http.client.NOT_MODIFIED])
                    self.req.setHeader('Cache-Control', 'public, no-cache')
                    self.req.setHeader('Content-Type', 'text/plain; charset=utf-8')
                    self.req.write('Same email')
                    return
                else:
                    return self.process_set_email(param_email)
            else:
                return self.process_set_email(param_email)
        else:
            session_email = req_session.get('email')
            if session_email is not None:
                try:
                    param_code = self.cgi_params.param_post('code')
                except self.cgi_params.NotFoundError:
                    param_code = None
                if param_code is not None:
                    return self.process_validate_code(param_code)
                else:
                    self.req.setResponseCode(http.client.BAD_REQUEST, http.client.responses[http.client.BAD_REQUEST])
                    self.req.setHeader('Cache-Control', 'public, no-cache')
                    self.req.setHeader('Content-Type', 'text/plain; charset=utf-8')
                    self.req.write('Session email set. Parameter code not supplied.')
                    return
            else:
                self.req.setResponseCode(http.client.BAD_REQUEST, http.client.responses[http.client.BAD_REQUEST])
                self.req.setHeader('Cache-Control', 'public, no-cache')
                self.req.setHeader('Content-Type', 'text/plain; charset=utf-8')
                self.req.write('Session email not set. Parameter email not supplied.')
                return

    def handle_get(self):
        req_session = self.req.context.session
        user_id = req_session.get('user_id')
        if user_id is not None:
            user = mod_mongo_user.UserDocument.objects(id=mod_mongo.bson.objectid.ObjectId(user_id)).get()
            if user is None:
                raise HandlerError('User not found', user_id)
            return self.render_user_view(user)
        else:
            session_email = req_session.get('email')
            if session_email is not None:
                session_code = req_session.get('code')
                if session_code is not None:
                    # code is saved as dict: {'value': 'XXXXXX', 'exp': datetime}
                    session_code_exp = session_code['exp']
                    if datetime.datetime.now(tz=datetime.UTC) >= session_code_exp:
                        del req_session['email']
                        del req_session['code']
                        req_session.save()
                        return self.render_auth_stage_email()
                    else:
                        return self.render_auth_stage_code()
                else:
                    raise HandlerError('Invalid session, email is set, code is not')
            else:
                return self.render_auth_stage_email()

    def process_set_email(self, email_address: str):
        user = mod_mongo_user.UserDocument.objects(email=email_address).get()
        if user is None:
            raise HandlerError('User not found')

        req_session = self.req.context.session
        req_session['email'] = email_address
        code = {
            'value': str(random.randint(100000, 999999)),
            'exp': datetime.datetime.now(tz=datetime.UTC) + dateutil.relativedelta.relativedelta(minutes=10),
        }
        req_session['code'] = code
        req_session.save()

        content = mod_tmpl_fs.TemplateFactory('email_code').render({'code': code['value'], 'exp': code['exp']})

        sender_name = str(email.header.Header(config.mail.from_name, 'utf-8'))
        sender_address = config.mail.from_email
        recipient_name = str(email.header.Header(user.name, 'utf-8'))
        recipient_address = user.email

        msg = email.mime.text.MIMEText(content, 'plain', 'utf-8')
        msg['From'] = email.utils.formataddr((sender_name, sender_address))
        msg['To'] = email.utils.formataddr((recipient_name, recipient_address))
        msg['Subject'] = str(email.header.Header('One-time access code', 'utf-8'))
        msg['X-Mailer'] = 'Python/Key Card Access System'

        mailer = smtplib.SMTP(config.mail.smtp_host, config.mail.smtp_port)
        mailer.sendmail(sender_address, recipient_address, msg.as_string())

        self.req.setResponseCode(http.client.OK, http.client.responses[http.client.OK])
        self.req.setHeader('Cache-Control', 'public, no-cache')
        self.req.setHeader('Content-Type', 'text/plain; charset=utf-8')
        self.req.write('Email set. Code sent.')

    def process_validate_code(self, code: str):
        req_session = self.req.context.session

        session_email = req_session.get('email')
        if session_email is None:
            raise HandlerError('Invalid session, email not set')

        session_code = req_session.get('code')
        if session_code is None:
            raise HandlerError('Invalid session, code not set')
        # code is saved as dict: {'value': 'XXXXXX', 'exp': datetime}
        session_code_value = session_code['value']
        session_code_exp = session_code['exp']

        if datetime.datetime.now(tz=datetime.UTC) >= session_code_exp:
            del req_session['email']
            del req_session['code']
            req_session.save()
            self.req.setResponseCode(http.client.GONE, http.client.responses[http.client.GONE])
            self.req.setHeader('Cache-Control', 'public, no-cache')
            self.req.setHeader('Content-Type', 'text/plain; charset=utf-8')
            self.req.write('Code expired. Session cleared.')
            return

        if session_code_value == code:
            user = mod_mongo_user.UserDocument.objects(email=session_email).get()
            if user is None:
                raise HandlerError('User not found')
            del req_session['email']
            del req_session['code']
            req_session['user_id'] = str(user.id)
            req_session.save()
            self.req.setResponseCode(http.client.ACCEPTED, http.client.responses[http.client.ACCEPTED])
            self.req.setHeader('Cache-Control', 'public, no-cache')
            self.req.setHeader('Content-Type', 'text/plain; charset=utf-8')
            self.req.write('Authenticated')
        else:
            self.req.setResponseCode(http.client.NOT_ACCEPTABLE, http.client.responses[http.client.NOT_ACCEPTABLE])
            self.req.setHeader('Cache-Control', 'public, no-cache')
            self.req.setHeader('Content-Type', 'text/plain; charset=utf-8')
            self.req.write('Not Authenticated')

    def render_user_view(self, user: mod_mongo_user.UserDocument):
        cards = list(mod_mongo_card.IssuedCard.objects(user_id=user.id))
        content = _skeleton.TemplateFactory(self.req, 'index').render({
            'user_name': user.name,
            'cards': cards,
        })
        self.req.setResponseCode(http.client.OK, http.client.responses[http.client.OK])
        self.req.setHeader('Cache-Control', 'public, no-cache')
        self.req.setHeader('Content-Type', 'text/html; charset=utf-8')
        self.req.write(content)

    def render_auth_stage_email(self):
        content = _skeleton.TemplateFactory(self.req, 'auth_stage_email').render({})
        self.req.setResponseCode(http.client.OK, http.client.responses[http.client.OK])
        self.req.setHeader('Cache-Control', 'public, no-cache')
        self.req.setHeader('Content-Type', 'text/html; charset=utf-8')
        self.req.write(content)

    def render_auth_stage_code(self):
        content = _skeleton.TemplateFactory(self.req, 'auth_stage_code').render({})
        self.req.setResponseCode(http.client.OK, http.client.responses[http.client.OK])
        self.req.setHeader('Cache-Control', 'public, no-cache')
        self.req.setHeader('Content-Type', 'text/html; charset=utf-8')
        self.req.write(content)

    @_deco_Session()
    def __call__(self):
        if self.req.method == 'POST':
            return self.handle_post()
        else:
            return self.handle_get()
