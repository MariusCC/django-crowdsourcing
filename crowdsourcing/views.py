from __future__ import absolute_import

import httplib
import logging

# django-viewutil
from djview import *

from .forms import forms_for_survey

def _survey_submit(request, survey):
    if not survey.is_open():
        # this should rarely if ever happen, since the form goes away when the survey is closed.
        return HttpResponseRedirect(reverse('survey_results', kwargs=dict(slug=survey.slug)))

    if survey.require_login and request.user.is_anonymous():
        # again, the form should only be shown after the user is logged in, but to be safe...
        return HttpResponseRedirect(reverse("auth_login") + '?next=%s' % request.path)
    if not hasattr(request, 'session'):
        return HttpResponse("Cookies must be enabled to use this application.", status=httplib.FORBIDDEN)
    if (not survey.allow_multiple_submissions and
        survey.submissions_for(request.user, request.session.session_key).count()):
        return render_with_request(['crowdsourcing/%s_already_submitted.html' % survey.slug,
                                    'crowdsourcing/already_submitted.html'],
                                   dict(survey=survey),
                                   request)

    forms=forms_for_survey(survey, request)
    if all(form.is_valid() for form in forms):
        for form in forms:
            form.save()
        # go to survey results/thanks page
        return _survey_results_redirect(request, survey, thanks=True)
    else:
        return _survey_show_form(request, survey, forms)

def _survey_show_form(request, survey, forms):
    return render_with_request(['crowdsourcing/%s_survey_detail.html' % survey.slug,
                                'crowdsourcing/survey_detail.html'],
                               dict(survey=survey, forms=forms),
                               request)


def survey_detail(request, slug):
    survey=get_object_or_404(Survey.live, slug=slug)

    if request.method=='POST':
        return _survey_submit(request, survey)

    can_show_form=survey.is_open and (request.user.is_authenticated() or not survey.require_login)
    if can_show_form:
        forms =forms_for_survey(survey, request)
    else:
        forms=()
    return _survey_show_form(request, survey, forms)


def survey_results(request, slug, page=None):
    if page is None:
        page=1
    else:
        page=get_int_or_404(page)
    survey=get_object_or_404(Survey.live, slug=slug)
    submissions=survey.public_submissions()
    paginator, page_obj=paginate_or_404(submissions, page)
    # clean this out?
    thanks=request.session.get('survey_thanks_%s' % slug)
    return render_with_request(['crowdsourcing/%s_survey_results.html' % slug,
                                'crowdsourcing/survey_results.html'],
                               dict(survey=survey,
                                    thanks=thanks,
                                    paginator=paginator,
                                    page_obj=page_obj),
                               request)
    

def _survey_results_redirect(request, survey, thanks=False):
    url=reverse('survey_results', kwargs={'slug': survey.slug})
    response=HttpResponseRedirect(url)
    if thanks:
        request.session['survey_thanks_%s' % survey.slug]='1'
    return response
