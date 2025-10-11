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
  
  # Hasta cuando está justificada su ausencia
  justification_end = fields.Boolean(default = False)