/**
 * Which comparison operators a screener field accepts, and which one to show.
 *
 * Extracted from app/screener/page.tsx so the rule can be tested. It carries
 * one decision that a customer reported before anyone else noticed it.
 *
 * A preset arrives from the API with its own operator — `market_cap gte 50`,
 * `debt_to_equity lte 0.5`. The screener also holds a list of field metadata
 * giving each field's type. The two arrive as independent requests.
 *
 * The previous code corrected a row's operator in the render body, treating
 * "I have no metadata for this field" the same as "this field is text". When
 * the preset request won the race, every field looked like text, `gte` is not
 * a text operator, and each preset's operator was overwritten with `eq` and
 * persisted. The field list then arrived, `eq` was valid for a number, and
 * nothing put the original back.
 *
 * The customer's words were: "the operator in the pre set screeners always
 * defaults to = usually returning zero results". `market_cap = 50` asks for a
 * company capitalised at exactly fifty million dollars.
 *
 * So an unknown field returns the stored operator untouched. Only a field
 * whose type is KNOWN, and whose stored operator that type cannot take, is
 * normalised — and even then the stored value is left alone and the valid one
 * is returned for display and for the request, which keeps those two in step.
 */

export interface OperatorChoice {
  value: string
  label: string
}

/** Operators per field type. The first is the default for a new row. */
export const OPERATORS: Record<string, OperatorChoice[]> = {
  number: [
    { value: 'gte', label: '>=' },
    { value: 'lte', label: '<=' },
    { value: 'gt', label: '>' },
    { value: 'lt', label: '<' },
    { value: 'eq', label: '=' },
    { value: 'neq', label: '≠' },
  ],
  boolean: [{ value: 'eq', label: 'is' }],
  text: [
    { value: 'eq', label: '=' },
    { value: 'neq', label: '≠' },
  ],
}

/** The operators a field of this type accepts. */
export function operatorsForType(type: string | undefined): OperatorChoice[] {
  return (type && OPERATORS[type]) || OPERATORS.text
}

/**
 * The operator to show for a row, and to send with its request.
 *
 * `fieldType` is the type from the loaded metadata, or `undefined` when the
 * field is not in it — which includes the case where the metadata has not
 * arrived. Undefined means unknown, never text.
 */
export function operatorFor(storedOperator: string,
                            fieldType: string | undefined): string {
  if (fieldType === undefined) return storedOperator
  const ops = operatorsForType(fieldType)
  return ops.some(o => o.value === storedOperator)
    ? storedOperator
    : ops[0].value
}
