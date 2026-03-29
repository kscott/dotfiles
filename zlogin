# Compile the completion dump in the background to speed up future startups.
{
  zcompdump="${ZDOTDIR:-$HOME}/.zcompdump"
  if [[ -s "$zcompdump" && (! -s "${zcompdump}.zwc" || "$zcompdump" -nt "${zcompdump}.zwc") ]]; then
    [[ -w "${zcompdump}.zwc" || ! -e "${zcompdump}.zwc" ]] && zcompile "$zcompdump"
  fi
} &!
