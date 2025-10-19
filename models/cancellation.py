# -*- coding: utf-8 -*-

from odoo import api, models, fields
from datetime import date

class Cancellation(models.Model):
  """
  Anulaciones de matrícula
  """
  _name = 'maya_students.cancellation'
  _description = 'Anulaciones de matrícula'
  
  # tipo de anulación, ordinaria o de oficio
  cancellation_type = fields.Selection([('ORD', 'Ordinaria'), ('OFC', 'Oficio')], required = True, default = 'ORD', string = 'Tipo')

  # situación de una anulación de oficio. Sólo para anulaciones de oficio
  situation = fields.Selection([
      ('0', ' '),
      ('1', 'Riesgo 1 - Sin notificar'),
      ('2', 'Riesgo 1 - Notificado'),
      ('3', 'Riesgo 2 - Pendiente de llamada'),
      ('4', 'Riesgo 2 - Llamada realizada'),
      ('5', 'Justificada'),
      ('6', 'Iniciado proceso de anulación'),
      ('7', 'Fin proceso de anulación'),
      ], string = 'Situación', default = '0',
      readonly = True)

  notification_date = fields.Date(string = 'Fecha de notificación por mail', 
                                    help = 'Fecha de notificación por mail')
  
  query_date = fields.Datetime(string = 'Fecha de la consulta', 
                                    help = 'Día y hora en el que se realizó la consulta a Moodle')
  
  lastaccess_date = fields.Datetime(string = 'Último acceso ', 
                                    help = 'Día y hora del último acceso al curso')
  
  # Hasta cuando está justificada su ausencia
  justification_end_date = fields.Date(string = 'Justificado hasta', 
                                    help = 'Fecha fin de la ajustificación')
  
  comments = fields.Text(string = 'Comentarios',
                         help = 'Información relativa a la razón de la justificación')
  
   # Relación 1:1 con subject_student_rel
  subject_student_rel_id = fields.Many2one(
      'maya_core.subject_student_rel',
      required=True,
      ondelete='cascade',  # Si se borra el subject_student_rel, se borra esta anulacioón
  )

  student_name = fields.Char(string = 'Alumno', related = 'subject_student_rel_id.student_id.student_info')
  student_nia = fields.Char(string = 'NIA', related = 'subject_student_rel_id.student_id.nia')
  student_email = fields.Char(string = 'Email', related = 'subject_student_rel_id.student_id.email')
  student_email_support = fields.Char(string = 'Email de apoyo', related = 'subject_student_rel_id.student_id.email_support')
  student_email_corp = fields.Char(string = 'Email corporativo', related = 'subject_student_rel_id.student_id.email_coorp')
  subject_name = fields.Char(string = 'Módulo', related = 'subject_student_rel_id.subject_id.name', store = True)
  subject_course = fields.Char(string = 'Ciclo', related = 'subject_student_rel_id.course_id.abbr', store = True)

  related_cancellations_ids = fields.One2many(
    'maya_students.cancellation',
    compute='_compute_related_cancellations',
    string='Otras anulaciones del alumno'
)

  _sql_constraints = [
    (
        'unique_subject_student_rel_id',
        'unique(subject_student_rel_id)',
        'Cada relación Subject-Student sólo puede tener una anulación de matrícula.'
    ),]
  
  @api.depends('subject_student_rel_id')
  def _compute_related_cancellations(self):
    for record in self:
        student = record.subject_student_rel_id.student_id
        if student:
            # Buscar todas las anulaciones del mismo estudiante
            cancellations = self.search([
                ('subject_student_rel_id.student_id', '=', student.id),
                ('id', '!=', record.id)
            ])
            record.related_cancellations_ids = cancellations
        else:
            record.related_cancellations_ids = False