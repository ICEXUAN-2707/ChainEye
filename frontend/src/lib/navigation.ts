export type WorkbenchView='review'|'diagnostic'|'research'|'run';

export function shortcutView(key:string,editable:boolean):WorkbenchView|null{
  if(editable)return null;
  return ({'1':'review','2':'diagnostic','3':'research','4':'run'} as Record<string,WorkbenchView>)[key]??null;
}
