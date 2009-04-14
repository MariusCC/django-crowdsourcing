from __future__ import absolute_import

import datetime
import logging
from operator import itemgetter

from django.contrib.auth.models import User
from django.db import models

from .geo import get_latitude_and_longitude
from .util import ChoiceEnum
from . import settings as local_settings

ARCHIVE_POLICY_CHOICES=ChoiceEnum(('immediate',
                                   'post-close',
                                   'never'))

class LiveSurveyManager(models.Manager):
    def get_query_set(self):
        now=datetime.datetime.now()
        return super(LiveSurveyManager, self).get_query_set().filter(
            is_published=True,
            starts_at__lte=now).filter(
            ~models.Q(archive_policy__exact=ARCHIVE_POLICY_CHOICES.NEVER) | 
            models.Q(ends_at__isnull=True) |
            models.Q(ends_at__gt=now))


class Survey(models.Model):
    title=models.CharField(max_length=80)
    slug=models.SlugField(unique=True)
    tease=models.TextField(blank=True)
    description=models.TextField(blank=True)
    
    require_login=models.BooleanField(default=False)
    allow_multiple_submissions=models.BooleanField(default=False)
    moderate_submissions=models.BooleanField(default=local_settings.MODERATE_SUBMISSIONS)
    archive_policy=models.results=models.IntegerField(choices=ARCHIVE_POLICY_CHOICES,
                                                      default=ARCHIVE_POLICY_CHOICES.IMMEDIATE)

    starts_at=models.DateTimeField(default=datetime.datetime.now)
    survey_date=models.DateField(blank=True, null=True, editable=False)
    ends_at=models.DateTimeField(null=True, blank=True)
    is_published=models.BooleanField(default=False)

    # Flickr integration
    flickr_set_id=models.CharField(max_length=60, blank=True)

    def save(self, **kwargs):
        self.survey_date=self.starts_at.date()
        super(Survey, self).save(**kwargs)

    class Meta:
        ordering=('-starts_at',)
        unique_together=(('survey_date', 'slug'),)

    @property
    def is_open(self):
        now=datetime.datetime.now()
        if self.ends_at:
            return self.starts_at <= now < self.ends_at
        else:
            return self.starts_at <= now

    def submissions_for(self, user, session_key):
        q=models.Q(survey=self)
        if user.is_authenticated():
            q=q & models.Q(user=user)
        elif session_key:
            q=q & models.Q(session_key=session_key)
        else:
            # can't pinpoint user, return none
            return Submission.objects.none()
        return Submission.objects.filter(q)

    def public_submissions(self):
        if self.archive_policy==ARCHIVE_POLICY_CHOICES.NEVER or (
            self.archive_policy==ARCHIVE_POLICY_CHOICES.POST_CLOSE and
            self.is_open):
            return self.submission_set.none()
        return self.submission_set.filter(is_public=True)

    def __unicode__(self):
        return self.title

    @models.permalink
    def get_absolute_url(self):
        return ('survey_detail', (), {'slug': self.slug })

    objects=models.Manager()
    live=LiveSurveyManager()
    
OPTION_TYPE_CHOICES = ChoiceEnum(sorted([('char', 'Text Field'),
                                         ('email', 'Email Field'),
                                         ('photo', 'Photo Upload'),
                                         ('video', 'Video Link'),
                                         ('location', 'Location Field'),
                                         ('integer', 'Integer'),
                                         ('float', 'Float'),
                                         ('bool', 'Boolean'),
                                         ('text', 'Text Area'),
                                         ('select', 'Select One Choice'),
                                         ('radio', 'Radio List'),
                                         ('checkbox', 'Checkbox List'),],
                                        key=itemgetter(1)))
                                 
class Question(models.Model):
    survey=models.ForeignKey(Survey, related_name="questions")
    fieldname=models.CharField(max_length=32)
    question=models.TextField()
    help_text=models.TextField(blank=True)
    required=models.BooleanField(default=False)
    order=models.IntegerField(null=True, blank=True)
    option_type=models.CharField(max_length=12, choices=OPTION_TYPE_CHOICES)
    options=models.TextField(blank=True, default='')
    answer_is_public=models.BooleanField(default=True)

    class Meta:
        ordering=('order',)
        unique_together=('fieldname', 'survey')


    def __unicode__(self):
        return self.question

    @property
    def parsed_options(self):
        return filter(None, (s.strip() for s in self.options.splitlines()))

class Submission(models.Model):
    survey=models.ForeignKey(Survey)
    user=models.ForeignKey(User, null=True)
    email=models.EmailField(blank=True, null=True)
    ip_address=models.IPAddressField()
    submitted_at=models.DateTimeField(default=datetime.datetime.now)
    session_key=models.CharField(max_length=40, blank=True, editable=False)

    # for moderation
    is_public=models.BooleanField(default=True)
    


    def get_answer_dict(self):
        try:
            # avoid called __getattr__
            return self.__dict__['_answer_dict']
        except KeyError:
            answers=self.answer_set.all()
            d=dict((a.question.fieldname, a.value) for a in answers)
            self.__dict__['_answer_dict']=d
            return d

    def __getattr__(self, k):
        d=self.get_answer_dict()
        try:
            return d[k]
        except KeyError:
            raise AttributeError("no such attribute: %s" % k)


class Answer(models.Model):
    submission=models.ForeignKey(Submission)
    question=models.ForeignKey(Question)
    text_answer=models.TextField(blank=True)
    integer_answer=models.IntegerField(null=True)
    float_answer=models.FloatField(null=True)
    boolean_answer=models.NullBooleanField()
    latitude=models.FloatField(blank=True, null=True)
    longitude=models.FloatField(blank=True, null=True)    

    def value():
        def get(self):
            ot=self.question.option_type
            if ot==OPTION_TYPE_CHOICES.BOOLEAN:
                return self.boolean_answer
            elif ot==OPTION_TYPE_CHOICES.FLOAT:
                return self.float_answer
            elif ot==OPTION_TYPE_CHOICES.INTEGER:
                return self.integer_answer
            return self.text_answer
        
        def set(self, v):
            ot=self.question.option_type
            if ot==OPTION_TYPE_CHOICES.BOOLEAN:
                self.boolean_answer=bool(v)
            elif ot==OPTION_TYPE_CHOICES.FLOAT:
                self.float_answer=float(v)
            elif ot==OPTION_TYPE_CHOICES.INTEGER:
                self.integer_answer=int(v)
            else:
                self.text_answer=v
                
        return get, set
    value=property(*value())

    class Meta:
        ordering=('question',)
    
    def __unicode__(self):
        return unicode(self.question)
