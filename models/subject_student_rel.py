# -*- coding: utf-8 -*-

from odoo import fields, models

class SubjectStudentRel(models.Model):
  """
  Ejemplo de herencia de clase
  Herencia del modelo maya_core.student
  Lo que hace es modificar el modelo maya_core.subject_student_rel para incluir 
  la anulacion de matricula (cancellation)
  se añadirá a la tabla maya_core.subject_student_rel de la base de datos
  Ese campo es accesible por cualquier otro módulo
  """
  _inherit = 'maya_core.subject_student_rel'

  # Relación 1:1 con cancelación
  cancellation_id = fields.One2many(
        'maya_students.cancellation',
        'subject_student_rel_id',
        string='Anulación',
    )
  
  def _compute_cancellation(self):
    """
    Asigna el usuario como primer elemento de la relación doble uno a muchos
    """
    for record in self:
      record.cancellation = record.cancellation_id[:1] if record.cancellation_id else False

